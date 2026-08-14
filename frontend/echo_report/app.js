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

  function setHidden(id, hidden) {
    var node = document.getElementById(id);
    if (node) {
      node.hidden = Boolean(hidden);
    }
  }

  function formatCount(value) {
    return String(Number(value) || 0).replace(
      /\B(?=(\d{3})+(?!\d))/g,
      ","
    );
  }

  function formatPercent(value) {
    return ((Number(value) || 0) * 100).toFixed(1) + "%";
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

  function formatReplyDuration(value) {
    var seconds = finiteNumber(value);
    if (seconds === null || seconds < 0) {
      return "时长未知";
    }
    if (seconds < 60) {
      return String(Math.round(seconds)) + " 秒";
    }
    return formatSessionDuration(seconds);
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
    setText(
      "overview-active-days",
      hasData && finiteNumber(overview.active_days) > 0
        ? formatCount(overview.active_days) + " 天"
        : "—"
    );
    setText(
      "overview-average-per-day",
      hasData && finiteNumber(overview.average_messages_per_active_day) !== null
        ? formatAverage(overview.average_messages_per_active_day) + " 条"
        : "—"
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

    // Viewer identity (secondary text, group only)
    var groupInitiators = sessions.group_initiators;
    var viewerIdentityReliable = sessions.viewer_identity_reliable;
    if (isGroup && viewerIdentityReliable && groupInitiators) {
      var selfCount = finiteNumber(groupInitiators.self_count);
      var selfShare = finiteNumber(groupInitiators.self_share);
      if (selfCount !== null && selfShare !== null) {
        setText(
          "session-viewer-identity",
          "你发起了 " + formatCount(selfCount) + " 轮，占 " + formatPercent(selfShare)
        );
        setHidden("session-viewer-identity", false);
      }
    } else {
      setHidden("session-viewer-identity", true);
    }

    // === Private mode: five-section narrative ===
    if (isPrivate) {
      // Hide old private layout remnants
      var privateBlock = document.getElementById("session-private-initiators");
      var unknownNote = document.getElementById("session-unknown-note");
      var oldFields = document.getElementById("session-fields-old");
      if (privateBlock) privateBlock.hidden = true;
      if (unknownNote) unknownNote.hidden = true;
      if (oldFields) oldFields.hidden = true;

      // 总览 / 第一句话
      setText("session-beat-title", "总览 · 第一句话");
      setHidden("session-beat", false);
      var initiators = sessions.private_initiators;
      var selfCount = initiators ? finiteNumber(initiators.self_count) : null;
      var peerCount = initiators ? finiteNumber(initiators.peer_count) : null;
      if (selfCount !== null && peerCount !== null && selfCount + peerCount > 0) {
        setText("session-group-top", "你开启 " + formatCount(selfCount) + " 轮 · TA 开启 " + formatCount(peerCount) + " 轮");
        setHidden("session-group-top", false);
      } else {
        setText("session-group-top", "");
        setHidden("session-group-top", true);
      }
      var selfPeakHour = finiteNumber(sessions.private_self_peak_start_hour);
      if (selfPeakHour !== null) {
        setText("session-self-peak-hour", "你最容易在 " + String(selfPeakHour) + ":00 左右开口");
        setHidden("session-self-peak-hour", false);
      } else {
        setHidden("session-self-peak-hour", true);
      }
      var peerPeakHour = finiteNumber(sessions.private_peer_peak_start_hour);
      if (peerPeakHour !== null) {
        setText("session-peer-peak-hour", "TA 最容易在 " + String(peerPeakHour) + ":00 左右开口");
        setHidden("session-peer-peak-hour", false);
      } else {
        setHidden("session-peer-peak-hour", true);
      }
      setHidden("session-peak-hour", true);

      // 接住第一句话
      var selfToPeer = finiteNumber(sessions.private_reply_median_self_to_peer_seconds);
      var peerToSelf = finiteNumber(sessions.private_reply_median_peer_to_self_seconds);
      var hasReplyData = selfToPeer !== null || peerToSelf !== null;
      setHidden("session-reply", !hasReplyData);
      setText("session-reply-self-to-peer", selfToPeer !== null ? "约 " + formatReplyDuration(selfToPeer) : "暂无足够样本");
      setText("session-reply-peer-to-self", peerToSelf !== null ? "约 " + formatReplyDuration(peerToSelf) : "暂无足够样本");

      // 一段乐句
      setHidden("session-movement", false);
      setText("session-median-duration", "约 " + formatSessionDuration(sessions.median_duration_seconds));
      setText("session-average-messages", "约 " + formatSessionMessages(sessions.average_message_count) + " 条");
      var charText = sessions.session_character;
      if (charText) {
        setText("session-character", charText);
        setHidden("session-character", false);
      } else {
        setHidden("session-character", true);
      }

      // 几段特别的聊天
      setText("session-highnotes-title", "几段特别的聊天");
      setHidden("session-highnotes", false);
      renderLoudest("session-loudest-messages", sessions.loudest_most_messages,
        function (s) {
          return formatSessionMessages(s.message_count) + " 条消息 · " + formatSessionDuration(s.duration_seconds);
        });
      renderLoudest("session-loudest-duration", sessions.loudest_longest_duration,
        function (s) {
          return formatSessionDuration(s.duration_seconds) + " · " + formatSessionMessages(s.message_count) + " 条消息";
        });
      renderLoudest("session-loudest-participants", null, function () { return ""; });
      renderLoudest("session-loudest-densest", sessions.loudest_densest,
        function (s) {
          return formatSessionMessages(s.message_count) + " 条消息 · " + formatSessionDuration(s.duration_seconds);
        });
      renderLoudest("session-loudest-back-and-forth", sessions.loudest_most_back_and_forth,
        function (s) {
          var selfMessages = finiteNumber(s.self_message_count);
          var peerMessages = finiteNumber(s.peer_message_count);
          var counts = "你 " + (selfMessages === null ? "—" : formatCount(selfMessages)) + " 条 · TA " + (peerMessages === null ? "—" : formatCount(peerMessages)) + " 条";
          return counts + " · " + formatSessionDuration(s.duration_seconds);
        });

      // 休止
      setHidden("session-rest", false);
      var thresholdSeconds = finiteNumber(sessions.threshold_seconds);
      var thresholdMinutes = thresholdSeconds !== null && thresholdSeconds > 0 ? Math.round(thresholdSeconds / 60) : 30;
      setText("session-threshold-note",
        "超过 " + String(thresholdMinutes) + " 分钟未继续交流，会视作下一轮聊天。"
      );
    }

    // === Group mode: 5-section narrative ===
    if (isGroup) {
      // Hide old private layout
      var privateBlock = document.getElementById("session-private-initiators");
      if (privateBlock) privateBlock.hidden = true;
      var unknownNote = document.getElementById("session-unknown-note");
      if (unknownNote) unknownNote.hidden = true;
      var oldFields = document.getElementById("session-fields-old");
      if (oldFields) oldFields.hidden = true;
      setHidden("session-reply", true);
      setHidden("session-self-peak-hour", true);
      setHidden("session-peer-peak-hour", true);

      // 谁来起拍
      setText("session-beat-title", "谁来起拍");
      setHidden("session-beat", false);
      if (groupInitiators && groupInitiators.top_member) {
        var topMember = groupInitiators.top_member;
        setText("session-group-top",
          "最常发起聊天：" + topMember.display_name +
          "（" + formatCount(topMember.count) + " 轮，" + formatPercent(topMember.share) + "）"
        );
      } else {
        setText("session-group-top", "");
      }
      var peakHour = finiteNumber(sessions.peak_start_hour);
      if (peakHour !== null) {
        setText("session-peak-hour", "聊天最容易从 " + String(peakHour) + ":00 左右开始");
        setHidden("session-peak-hour", false);
      } else {
        setHidden("session-peak-hour", true);
      }

      // 一段乐句
      setHidden("session-movement", false);
      setText("session-median-duration", "约 " + formatSessionDuration(sessions.median_duration_seconds));
      setText("session-average-messages", "约 " + formatSessionMessages(sessions.average_message_count) + " 条");
      var charText = sessions.session_character;
      if (charText) {
        setText("session-character", charText);
        setHidden("session-character", false);
      } else {
        setHidden("session-character", true);
      }

      // 聊天里的几个高音
      setText("session-highnotes-title", "聊天里的几个高音");
      setHidden("session-highnotes", false);
      renderLoudest("session-loudest-messages", sessions.loudest_most_messages,
        function (s) {
          return formatSessionMessages(s.message_count) + " 条消息 · " + formatSessionDuration(s.duration_seconds);
        });
      renderLoudest("session-loudest-duration", sessions.loudest_longest_duration,
        function (s) {
          return formatSessionDuration(s.duration_seconds) + " · " + formatSessionMessages(s.message_count) + " 条消息";
        });
      renderLoudest("session-loudest-participants", sessions.loudest_most_participants,
        function (s) {
          return String(s.participant_count) + " 人参与 · " + formatSessionMessages(s.message_count) + " 条消息";
        });
      renderLoudest("session-loudest-densest", sessions.loudest_densest,
        function (s) {
          return formatSessionMessages(s.message_count) + " 条消息 · " + formatSessionDuration(s.duration_seconds);
        });
      renderLoudest("session-loudest-back-and-forth", null, function () { return ""; });

      // 休止
      setHidden("session-rest", false);
      var thresholdSeconds = finiteNumber(sessions.threshold_seconds);
      var thresholdMinutes = thresholdSeconds !== null && thresholdSeconds > 0 ? Math.round(thresholdSeconds / 60) : 30;
      setText("session-threshold-note",
        "超过 " + String(thresholdMinutes) + " 分钟未继续交流，会视作下一轮聊天。"
      );
    }
  }

  function formatTimestamp(ts) {
    if (ts === null || ts === undefined || ts === "") {
      return null;
    }
    var d = new Date(Number(ts) * 1000);
    if (isNaN(d.getTime())) return null;
    var y = String(d.getFullYear()).slice(-2);
    var m = String(d.getMonth() + 1);
    var day = String(d.getDate());
    var hh = String(d.getHours()).padStart(2, "0");
    var mm = String(d.getMinutes()).padStart(2, "0");
    return y + "/" + m + "/" + day + " \u00b7 " + hh + ":" + mm;
  }

    function renderLoudest(containerId, session, formatFn) {
    var container = document.getElementById(containerId);
    if (!container) return;
    if (session && session.message_count > 0) {
      container.hidden = false;
      var textId = containerId + "-text";
      var textNode = document.getElementById(textId);
      if (textNode) {
        textNode.textContent = formatFn(session);
      }
      // Set time anchor
      var timeId = containerId + "-time";
      var timeNode = document.getElementById(timeId);
      if (timeNode) {
        var ts = formatTimestamp(session.start_timestamp);
        if (ts) {
          timeNode.textContent = ts;
          timeNode.hidden = false;
        } else {
          timeNode.hidden = true;
        }
      }
    } else {
      container.hidden = true;
    }
  }  var hourly = (data && data.activity && data.activity.hourly) || [];
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

  var languageProfile = data && data.language_profile;
  var languageMode = languageProfile && languageProfile.mode;
  setText(
    "voices-intro",
    languageMode === "group_distinctive"
      ? "在这段聊天里，这些词更像 TA。它们只描述当前时间范围与当前群聊。"
      : languageMode === "private_common"
        ? "你们反复说起的词，像两种声音在这段聊天里留下的回声。"
        : "会话类型明确后，才能选择合适的语言画像。"
  );

  function appendWords(parent, words) {
    var list = document.createElement("ol");
    list.className = "voice-words";
    (words || []).forEach(function (word) {
      var item = document.createElement("li");
      item.textContent = word;
      list.appendChild(item);
    });
    parent.appendChild(list);
  }

  var memberList = document.getElementById("member-list");
  if (memberList) {
    memberList.textContent = "";
    memberList.className =
      "member-list" +
      (languageMode === "private_common" ? " mode-private" : " mode-group");
    if (!languageProfile || !languageProfile.available) {
      var unavailable = document.createElement("p");
      unavailable.className = "language-unavailable";
      unavailable.textContent =
        (languageProfile && languageProfile.unavailable_reason) ||
        emptyDescription ||
        "暂无可展示的语言画像。";
      memberList.appendChild(unavailable);
    } else {
      (languageProfile.members || []).forEach(function (member, index) {
        var article = document.createElement("article");
        article.className = "voice-entry";

        var header = document.createElement("header");
        var number = document.createElement("span");
        number.className = "member-index";
        number.textContent =
          index < 9 ? "0" + String(index + 1) : String(index + 1);
        var heading = document.createElement("h3");
        heading.textContent = member.heading || member.display_name || "成员";
        header.appendChild(number);
        header.appendChild(heading);
        article.appendChild(header);

        if (languageMode === "group_distinctive") {
          var descriptor = document.createElement("p");
          descriptor.className = "voice-descriptor";
          descriptor.textContent = "在这段聊天里，这些词更像 TA";
          article.appendChild(descriptor);
        }
        appendWords(article, member.primary_words);

        if (languageMode === "group_distinctive" && member.context_words.length) {
          var context = document.createElement("p");
          context.className = "voice-context";
          context.textContent = "常聊：" + member.context_words.join(" · ");
          article.appendChild(context);
        }
        if (languageMode === "private_common" && member.expression_habits) {
          var habits = member.expression_habits;
          var habitLine = document.createElement("p");
          habitLine.className = "voice-context";
          habitLine.textContent =
            "平均 " + formatSessionMessages(habits.average_length) + " 字 · " +
            "中位 " + formatSessionMessages(habits.median_length) + " 字 · " +
            "最长 " + formatCount(habits.max_length) + " 字 · " +
            "一次连发 " + formatSessionMessages(habits.average_run_length) + " 条";
          article.appendChild(habitLine);
        }
        memberList.appendChild(article);
      });
    }
  }

  var sharedWordsBlock = document.getElementById("private-shared-words");
  var sideWordsBlock = document.getElementById("private-side-words");
  var sharedWordsList = document.getElementById("private-shared-words-list");
  var sideWordsList = document.getElementById("private-side-words-list");
  if (sharedWordsBlock) sharedWordsBlock.hidden = true;
  if (sideWordsBlock) sideWordsBlock.hidden = true;
  if (sharedWordsList) sharedWordsList.textContent = "";
  if (sideWordsList) sideWordsList.textContent = "";
  if (
    languageMode === "private_common" &&
    languageProfile &&
    languageProfile.available &&
    sharedWordsBlock &&
    sharedWordsList
  ) {
    var sharedWords = languageProfile.shared_words || [];
    if (sharedWords.length) {
      sharedWordsBlock.hidden = false;
      sharedWords.forEach(function (item) {
        var entry = document.createElement("li");
        var selfCount = finiteNumber(item.self_count);
        var peerCount = finiteNumber(item.peer_count);
        entry.textContent =
          item.word + " · 你 " + (selfCount === null ? "—" : formatCount(selfCount)) +
          " 次 · TA " + (peerCount === null ? "—" : formatCount(peerCount)) + " 次";
        sharedWordsList.appendChild(entry);
      });
    }
  }
  if (
    languageMode === "private_common" &&
    languageProfile &&
    languageProfile.available &&
    sideWordsBlock &&
    sideWordsList
  ) {
    var sideWords = languageProfile.side_preference_words || [];
    if (sideWords.length) {
      sideWordsBlock.hidden = false;
      sideWords.forEach(function (item) {
        var entry = document.createElement("li");
        var sideLabel = item.emphasis === "self" ? "你更常说" : "TA 更常说";
        entry.textContent = item.word + " · " + sideLabel;
        sideWordsList.appendChild(entry);
      });
    }
  }

  var expressionCulture = data && data.expression_culture;
  var expressionChapter = document.getElementById("expression");
  var expressionToc = document.getElementById("expression-toc");
  var expressionTopList = document.getElementById("expression-top-list");
  var expressionMembers = document.getElementById("expression-members");
  var hasExpressionCulture = Boolean(
    expressionCulture && expressionCulture.available
  );
  if (expressionChapter) {
    expressionChapter.hidden = !hasExpressionCulture;
  }
  if (expressionToc) {
    expressionToc.hidden = !hasExpressionCulture;
  }
  if (hasExpressionCulture) {
    setText("expression-intro", "表情在这段交流里留下的共同语言。");
    setText(
      "expression-message-count",
      formatCount(expressionCulture.expression_message_count) + " 条"
    );
    setText(
      "expression-only-count",
      formatCount(expressionCulture.expression_only_message_count) + " 条"
    );
    setText(
      "expression-unique-count",
      formatCount(expressionCulture.unique_expression_count) + " 种"
    );
    if (expressionTopList) {
      expressionTopList.textContent = "";
      (expressionCulture.top_expressions || []).forEach(function (item) {
        var entry = document.createElement("li");
        entry.textContent = item.display_text;
        var count = document.createElement("strong");
        count.textContent = formatCount(item.count) + " 次";
        entry.appendChild(count);
        expressionTopList.appendChild(entry);
      });
    }
    if (expressionMembers) {
      expressionMembers.textContent = "";
      (expressionCulture.members || []).forEach(function (member) {
        var article = document.createElement("article");
        article.className = "expression-member";
        var header = document.createElement("header");
        var name = document.createElement("h3");
        name.textContent = member.display_name;
        header.appendChild(name);
        article.appendChild(header);
        var share = finiteNumber(member.expression_share_percent);
        var shareText = share === null ? "—" : share.toFixed(1) + "%";
        var summary = document.createElement("p");
        summary.className = "expression-summary";
        summary.textContent =
          "表情 " + formatCount(member.expression_occurrence_count) + " 次 · 占全部表情 " +
          shareText + " · 带表情消息 " +
          formatCount(member.expression_message_count) + " 条";
        article.appendChild(summary);
        var memberList = document.createElement("ul");
        memberList.className = "expression-list";
        (member.top_expressions || []).forEach(function (item) {
          var entry = document.createElement("li");
          entry.textContent = item.display_text;
          var count = document.createElement("strong");
          count.textContent = formatCount(item.count) + " 次";
          entry.appendChild(count);
          memberList.appendChild(entry);
        });
        article.appendChild(memberList);
        expressionMembers.appendChild(article);
      });
    }
  }
})();
