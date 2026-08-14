"use strict";

document.documentElement.classList.add("js-ready");

(function () {
  "use strict";

  var data = window.ECHO_DATA || null;
  var overview = data && data.overview ? data.overview : null;
  var conversation = data && data.conversation ? data.conversation : null;
  var hasData = Boolean(overview && overview.has_data);
  var emptyDescription =
    overview && overview.empty_description ? overview.empty_description : "";

  function setText(id, value) {
    var node = document.getElementById(id);
    if (node) {
      node.textContent = value;
    }
  }

  function formatCount(value) {
    return String(Number(value) || 0).replace(
      /\B(?=(\d{3})+(?!\d))/g,
      ","
    );
  }

  function formatPercent(value) {
    return (Number(value) || 0).toFixed(1) + "%";
  }

  function formatAverage(value) {
    return (Number(value) || 0).toFixed(1);
  }

  function finiteNumber(value) {
    if (value === null || value === "" || typeof value === "boolean") {
      return null;
    }
    var number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function formatSessionDuration(value) {
    var seconds = finiteNumber(value);
    if (seconds === null || seconds < 0) {
      return "时长未知";
    }
    var totalMinutes = Math.round(seconds / 60);
    if (totalMinutes < 60) {
      return String(totalMinutes) + " 分钟";
    }
    var hours = Math.floor(totalMinutes / 60);
    var minutes = totalMinutes % 60;
    return (
      String(hours) + " 小时" +
      (minutes ? " " + String(minutes) + " 分钟" : "")
    );
  }

  function formatSessionMessages(value) {
    var count = finiteNumber(value);
    if (count === null || count < 0) {
      return "消息数未知";
    }
    return Number.isInteger(count) ? String(count) : count.toFixed(1);
  }

  document.querySelectorAll("[data-current-year]").forEach(function (element) {
    element.textContent = String(new Date().getFullYear());
  });

  var title =
    (data && data.title) ||
    (conversation && conversation.name) ||
    "余音 Echo · 聊天记忆报告";
  setText("cover-title", title);
  if (data && data.title) {
    document.title = data.title + " · 余音 Echo";
  }

  var timeSpan =
    conversation && conversation.time_span ? conversation.time_span : "";
  var coverRange = document.getElementById("cover-range");
  if (coverRange) {
    coverRange.textContent = timeSpan ? timeSpan : "本地生成";
    coverRange.hidden = !timeSpan;
  }

  if (overview) {
    setText(
      "overview-message-count",
      hasData ? formatCount(overview.total_message_count) : "—"
    );
    setText("overview-time-span", timeSpan ? timeSpan : "—");
    setText(
      "overview-participants",
      hasData ? formatCount(overview.participant_count) + " 人" : "—"
    );
    if (!hasData && emptyDescription) {
      setText("overview-intro", emptyDescription);
    }
  }

  var sessions = data && data.conversation_sessions;
  var sessionsToc = document.getElementById("session-toc");
  var sessionsChapter = document.getElementById("conversation-sessions");
  var sessionCount = sessions ? finiteNumber(sessions.session_count) : null;
  var hasSessions = Boolean(
    sessions && sessionCount !== null && sessionCount > 0
  );
  if (sessionsChapter) {
    sessionsChapter.hidden = !hasSessions;
  }
  if (sessionsToc) {
    sessionsToc.hidden = !hasSessions;
  }
  if (hasSessions) {
    var conversationKind = conversation && conversation.kind;
    var isPrivate = conversationKind === "private";
    var isGroup = conversationKind === "group";
    setText(
      "session-lead",
      isPrivate
        ? "过去这段时间，你们一共聊起了 " + formatCount(sessionCount) + " 轮"
        : isGroup
          ? "过去这段时间，群里一共聊起了 " + formatCount(sessionCount) + " 轮"
          : "过去这段时间，一共聊起了 " + formatCount(sessionCount) + " 轮"
    );
    setText(
      "session-median-duration",
      "通常一次会聊约 " +
        formatSessionDuration(sessions.median_duration_seconds)
    );
    setText(
      "session-longest-duration",
      "最长的一次持续 " +
        formatSessionDuration(sessions.longest_duration_seconds)
    );
    setText(
      "session-average-messages",
      "平均每轮约 " +
        formatSessionMessages(sessions.average_message_count) +
        " 条消息"
    );

    var thresholdSeconds = finiteNumber(sessions.threshold_seconds);
    var thresholdMinutes =
      thresholdSeconds !== null && thresholdSeconds > 0
        ? Math.round(thresholdSeconds / 60)
        : 30;
    setText(
      "session-threshold-note",
      "相隔超过 " +
        String(thresholdMinutes) +
        " 分钟未继续交流，会被视为一段新的聊天。"
    );

    var privateBlock = document.getElementById("session-private-initiators");
    var unknownNote = document.getElementById("session-unknown-note");
    var initiators = isPrivate ? sessions.private_initiators : null;
    var selfShare = initiators ? finiteNumber(initiators.self_share) : null;
    var peerShare = initiators ? finiteNumber(initiators.peer_share) : null;
    var selfCount = initiators ? finiteNumber(initiators.self_count) : null;
    var peerCount = initiators ? finiteNumber(initiators.peer_count) : null;
    var unknownCount = initiators
      ? finiteNumber(initiators.unknown_count)
      : null;
    var hasKnownInitiators = Boolean(
      isPrivate &&
      selfShare !== null &&
      peerShare !== null &&
      selfCount !== null &&
      peerCount !== null &&
      selfCount + peerCount > 0
    );
    if (privateBlock) {
      privateBlock.hidden = !hasKnownInitiators;
    }
    setText(
      "session-self",
      hasKnownInitiators
        ? "你先开口 " +
            formatPercent(selfShare * 100) +
            "（" +
            formatCount(selfCount) +
            " 次）"
        : ""
    );
    setText(
      "session-peer",
      hasKnownInitiators
        ? "对方先开口 " +
            formatPercent(peerShare * 100) +
            "（" +
            formatCount(peerCount) +
            " 次）"
        : ""
    );
    if (unknownNote) {
      unknownNote.hidden = !(isPrivate && unknownCount > 0);
      unknownNote.textContent =
        isPrivate && unknownCount > 0
          ? "有 " +
            formatCount(unknownCount) +
            " 轮暂时无法判断谁先开口。"
          : "";
    }

    var groupBlock = document.getElementById("session-group-initiators");
    var groupInitiators = isGroup ? sessions.group_initiators : null;
    var groupSelfCount = groupInitiators
      ? finiteNumber(groupInitiators.self_count)
      : null;
    var groupSelfShare = groupInitiators
      ? finiteNumber(groupInitiators.self_share)
      : null;
    var topMember = groupInitiators && groupInitiators.top_member;
    var topMemberName =
      topMember && typeof topMember.display_name === "string"
        ? topMember.display_name.trim()
        : "";
    var topMemberCount = topMember ? finiteNumber(topMember.count) : null;
    var topMemberShare = topMember ? finiteNumber(topMember.share) : null;
    var hasGroupSelf = Boolean(
      isGroup && groupSelfCount !== null && groupSelfShare !== null
    );
    var hasTopMember = Boolean(
      isGroup &&
      topMemberName &&
      topMemberCount !== null &&
      topMemberShare !== null
    );
    if (groupBlock) {
      groupBlock.hidden = !(hasGroupSelf || hasTopMember);
    }
    setText(
      "session-group-self",
      hasGroupSelf
        ? "你发起了 " +
            formatCount(groupSelfCount) +
            " 轮，占 " +
            formatPercent(groupSelfShare * 100)
        : ""
    );
    setText(
      "session-group-top",
      hasTopMember
        ? "最常发起聊天：" +
            topMemberName +
            "（" +
            formatCount(topMemberCount) +
            " 轮，" +
            formatPercent(topMemberShare * 100) +
            "）"
        : ""
    );
  }

  var hourly = (data && data.activity && data.activity.hourly) || [];
  var busiestBlock = document.getElementById("busiest-hour");
  if (busiestBlock) {
    var peak = null;
    hourly.forEach(function (point) {
      if (!peak || Number(point.value) > Number(peak.value)) {
        peak = point;
      }
    });
    if (hasData && peak && peak.label) {
      busiestBlock.textContent = peak.label;
      busiestBlock.hidden = false;
    } else {
      busiestBlock.hidden = true;
    }
  }

  var hourBars = document.getElementById("hour-bars");
  if (hourBars) {
    hourBars.textContent = "";
    if (hasData && hourly.length) {
      var maxHour = 0;
      hourly.forEach(function (point) {
        maxHour = Math.max(maxHour, Number(point.value) || 0);
      });
      hourly.forEach(function (point) {
        var value = Number(point.value) || 0;
        var bar = document.createElement("i");
        bar.style.setProperty(
          "--v",
          String(maxHour > 0 ? Math.round((value / maxHour) * 100) : 0)
        );
        if (maxHour > 0 && value === maxHour) {
          bar.className = "peak";
        }
        hourBars.appendChild(bar);
      });
    }
  }

  var weekdayTracks = document.getElementById("weekday-tracks");
  var weekday = (data && data.activity && data.activity.weekday) || [];
  if (weekdayTracks) {
    weekdayTracks.textContent = "";
    if (hasData && weekday.length) {
      var maxWeekday = 0;
      weekday.forEach(function (point) {
        maxWeekday = Math.max(maxWeekday, Number(point.value) || 0);
      });
      weekday.forEach(function (point) {
        var value = Number(point.value) || 0;
        var row = document.createElement("div");
        var label = document.createElement("span");
        label.textContent = point.label;
        var track = document.createElement("b");
        var fill = document.createElement("i");
        fill.style.setProperty(
          "--v",
          String(maxWeekday > 0 ? Math.round((value / maxWeekday) * 100) : 0) + "%"
        );
        track.appendChild(fill);
        var count = document.createElement("em");
        count.textContent = formatCount(value);
        row.appendChild(label);
        row.appendChild(track);
        row.appendChild(count);
        weekdayTracks.appendChild(row);
      });
    }
  }

  var memberList = document.getElementById("member-list");
  var members = (data && data.members) || [];
  if (memberList) {
    memberList.textContent = "";
    members.forEach(function (member, index) {
      var article = document.createElement("article");
      article.className =
        "member-entry" + (member.is_viewer ? " is-viewer" : "");

      var header = document.createElement("header");
      var number = document.createElement("span");
      number.className = "member-index";
      number.textContent =
        index < 9 ? "0" + String(index + 1) : String(index + 1);
      var nameBlock = document.createElement("div");
      var name = document.createElement("h3");
      name.textContent = member.display_name || "成员";
      var subtitle = document.createElement("p");
      subtitle.textContent = "本地聊天成员";
      nameBlock.appendChild(name);
      nameBlock.appendChild(subtitle);
      header.appendChild(number);
      header.appendChild(nameBlock);
      if (member.is_viewer) {
        var mark = document.createElement("span");
        mark.className = "viewer-mark";
        mark.textContent = "这是你";
        header.appendChild(mark);
      }
      article.appendChild(header);

      var dl = document.createElement("dl");
      var fields = [
        ["消息数量", formatCount(member.message_count)],
        ["占比", formatPercent(member.message_share_percent)],
        ["平均长度", formatAverage(member.average_length)],
        ["活跃时间", member.active_period || "—"]
      ];
      fields.forEach(function (field) {
        var div = document.createElement("div");
        var dt = document.createElement("dt");
        dt.textContent = field[0];
        var dd = document.createElement("dd");
        dd.textContent = field[1];
        div.appendChild(dt);
        div.appendChild(dd);
        dl.appendChild(div);
      });
      article.appendChild(dl);

      var rhythm = document.createElement("div");
      rhythm.className = "member-rhythm";
      var memberHourly = (member.activity && member.activity.hourly) || [];
      var activeIndexes = [];
      memberHourly.forEach(function (point, pointIndex) {
        if (Number(point.value) > 0) {
          activeIndexes.push(pointIndex);
        }
      });
      if (activeIndexes.length && memberHourly.length === 24) {
        var startIndex = activeIndexes[0];
        var endIndex = activeIndexes[activeIndexes.length - 1];
        var segment = document.createElement("i");
        segment.style.setProperty(
          "--start",
          ((startIndex / 24) * 100).toFixed(1) + "%"
        );
        segment.style.setProperty(
          "--width",
          (((endIndex - startIndex + 1) / 24) * 100).toFixed(1) + "%"
        );
        rhythm.appendChild(segment);
      }
      article.appendChild(rhythm);

      memberList.appendChild(article);
    });

    if (hasData && !members.length) {
      var note = document.createElement("p");
      note.className = "chapter-intro";
      note.textContent =
        emptyDescription || "没有可展示的成员数据。";
      memberList.appendChild(note);
    }
  }
})();
