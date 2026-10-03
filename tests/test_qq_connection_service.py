"""Desktop readiness probes use only Echo NapCat status; no QCE API."""
from dataclasses import FrozenInstanceError
import pytest
from qq_chat_analyzer.application.qq.qq_connection_service import QQConnectionService, QQConnectionStatus
from qq_chat_analyzer.application.qq.qq_environment_config import QQConfigCorrupted, QQConfigNotFound
from qq_chat_analyzer.providers.napcat_qq_provider import NapCatQQProvider, NapCatStatus

@pytest.mark.parametrize("bridge,online,uin,passphrase,available,direct", [
    (True,True,"12345678",True,True,True),
    (True,True,"12345678",False,True,False),
    (True,False,"12345678",True,False,False),
    (False,True,"12345678",True,False,False),
    (True,True,"u_uid",True,False,False),
])
def test_single_status_probe_separates_login_and_database(monkeypatch,bridge,online,uin,passphrase,available,direct):
    provider=NapCatQQProvider();calls=[]
    def probe():
        calls.append(1)
        return NapCatStatus(bridge,online,{"uin":uin},True,passphrase,True)
    monkeypatch.setattr(provider,"status",probe)
    result=QQConnectionService(provider).check_status()
    assert result.available is available and result.qq_online is available
    assert result.runtime_running is bridge and result.direct_db_ready is direct
    assert result.message and result.action_hint and calls==[1]

def test_provider_error_is_safe(monkeypatch):
    provider=NapCatQQProvider()
    def failed(): raise RuntimeError("fictional-secret")
    monkeypatch.setattr(provider,"status",failed)
    result=QQConnectionService(provider).check_status()
    assert not result.available and not result.runtime_running
    assert "fictional-secret" not in result.message

@pytest.mark.parametrize("error",[QQConfigNotFound(),QQConfigCorrupted(),RuntimeError("fictional-secret")])
def test_factory_errors_remain_user_safe(error):
    class Factory:
        def create(self): raise error
    result=QQConnectionService(provider_factory=Factory()).check_status()
    assert not result.available and result.message and result.action_hint
    assert "fictional-secret" not in result.message

def test_status_is_immutable():
    result=QQConnectionStatus(True,True,True,None,"ready","analyze")
    with pytest.raises(FrozenInstanceError): result.message="changed"
