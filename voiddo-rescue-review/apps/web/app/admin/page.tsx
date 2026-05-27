import { fetchJson, postJson } from "../lib/api";
import { headers } from "next/headers";

const labels: Record<string, string> = {
  leads_total: "leads total",
  qualified_leads: "qualified",
  audit_pages_generated: "audit pages",
  payments: "payments",
  subscriptions: "subscriptions",
  customers: "customers",
  fix_requests: "fix requests",
  human_review_required: "human review",
};

export default async function AdminPage() {
  async function runMailerOpsAction(formData: FormData) {
    "use server";
    const action = String(formData.get("action") || "");
    const limit = Number(formData.get("limit") || 10);
    await postJson("/admin/mailer/ops-actions", { action, limit });
  }

  const requestHeaders = await headers();
  const authorization = requestHeaders.get("authorization") || "";
  const data = await fetchJson("/admin/metrics", authorization ? { Authorization: authorization } : {});
  const mailerData = await fetchJson("/admin/mailer/control-room", authorization ? { Authorization: authorization } : {});
  const recheckData = await fetchJson("/admin/mailer/clean-window-recheck", authorization ? { Authorization: authorization } : {});
  const postWindowData = await fetchJson("/admin/mailer/post-window-recheck", authorization ? { Authorization: authorization } : {});
  const ledgerData = await fetchJson("/admin/mailer/autonomy-ledger", authorization ? { Authorization: authorization } : {});
  const actionQueueData = await fetchJson("/admin/mailer/action-queue", authorization ? { Authorization: authorization } : {});
  const closedLoopData = await fetchJson("/admin/mailer/closed-loop", authorization ? { Authorization: authorization } : {});
  const simulationData = await postJson("/admin/mailer/customer-simulation", { write_report: false }, authorization ? { Authorization: authorization } : {});
  const opsActionData = await fetchJson("/admin/mailer/ops-actions", authorization ? { Authorization: authorization } : {});
  const opsRetentionHistoryData = await fetchJson("/admin/mailer/ops-retention-history", authorization ? { Authorization: authorization } : {});
  const digestData = await fetchJson("/admin/mailer/digest-summary", authorization ? { Authorization: authorization } : {});
  const trendGuardData = await fetchJson("/admin/mailer/digest-trend-guard/latest", authorization ? { Authorization: authorization } : {});
  const monitoringData = await fetchJson("/admin/monitoring/summary", authorization ? { Authorization: authorization } : {});
  const metrics = data || {};
  const mailer = mailerData?.control_room || {};
  const recheck = recheckData?.summary || {};
  const postWindow = postWindowData?.summary || {};
  const ledger = ledgerData?.ledger || {};
  const actionQueue = actionQueueData?.queue || {};
  const closedLoop = closedLoopData?.closed_loop || {};
  const simulation = simulationData?.simulation || {};
  const opsActions = opsActionData?.ops_actions || {};
  const opsRetentionHistory = opsRetentionHistoryData?.history || {};
  const latestOpsRetentionHistory = opsRetentionHistory.latest || {};
  const digest = digestData?.digest || {};
  const digestOps = digest.mailer_ops || {};
  const digestReport = digest.digest_agent_report || {};
  const digestHistory = digest.digest_agent_history || {};
  const latestDigestHistory = digestHistory.latest || {};
  const digestOpsRetentionHistory = digest.mailer_ops_retention_history || {};
  const latestDigestOpsRetentionHistory = digestOpsRetentionHistory.latest || {};
  const trendGuard = trendGuardData?.trend_guard || {};
  const trendQueue = trendGuard.queue_hygiene || {};
  const latestRealOpsAction = opsActions.latest_real || {};
  const opsRetentionAgent = opsActions.latest_retention_agent || {};
  const opsRetentionReport = opsActions.retention_agent_report || {};
  const monitoring = monitoringData?.summary || {};
  const cards = Object.entries(labels).map(([key, label]) => [String(metrics[key] ?? 0), label]);
  const scans = metrics.scans || {};
  const emails = metrics.emails || {};
  const switches = metrics.kill_switches || {};
  const latestMailer = metrics.latest_mailer_status || {};
  const mailerSignals = mailer.signals || {};
  const mailerWarmup = mailer.warmup || {};
  const mailerLessons = mailer.lessons || [];
  const cleanRecovery = mailer.latest_clean_window_recovery || {};
  const ledgerGates = ledger.gates || {};
  const ledgerOwner = ledger.owner_commands || {};
  const ledgerInbound = ledger.inbound || {};
  const ledgerOutbound = ledger.outbound || {};
  const ledgerThrottle = ledger.throttle || {};
  const actionCounts = Array.isArray(actionQueue.counts) ? actionQueue.counts : [];
  const customerMailCounts = actionCounts.filter((item: any) => ["customer_onboarding", "fix_request_created", "monitoring_report"].includes(item.action_type));
  const sendLedger = closedLoop.send_ledger || actionQueue.send_ledger || {};
  const closedLoopSignals = closedLoop.signals || {};
  const monitoringStatuses = monitoring.target_statuses || [];
  const monitoringRuns = monitoring.latest_runs || [];
  const ops = [
    ["scouts", metrics.scout_runs ?? 0],
    ["campaigns", metrics.campaigns ?? 0],
    ["agents", metrics.agent_runs ?? 0],
    ["onboarding", metrics.onboarding_tasks ?? 0],
  ];
  const selfOps = [
    ["economics", metrics.economics_snapshots ?? 0],
    ["self audits", metrics.self_audit_runs ?? 0],
    ["fix queue", metrics.self_fix_tasks_open ?? 0],
    ["learning", metrics.self_learning_events ?? 0],
    ["build queue", metrics.self_build_queue_open ?? 0],
    ["mailer decisions", metrics.autonomous_mailer_decisions ?? 0],
    ["outbound gates", metrics.outbound_mailer_decisions ?? 0],
    ["mailer drafts", metrics.mailer_drafts ?? 0],
    ["reply plans", metrics.reply_action_plans ?? 0],
    ["plugin gates", metrics.quality_plugin_runs ?? 0],
    ["simulations", metrics.revenue_simulation_runs ?? 0],
    ["clean windows", metrics.mail_clean_window_checks ?? 0],
    ["campaign readiness", metrics.campaign_readiness_snapshots ?? 0],
    ["clean transitions", metrics.mail_clean_window_transitions ?? 0],
    ["mailbox health", metrics.mailbox_health_scores ?? 0],
    ["sender rotation", metrics.sender_rotation_readiness ?? 0],
    ["spacing repairs", metrics.warmup_schedule_repairs ?? 0],
    ["spacing rollbacks", metrics.warmup_schedule_rollbacks ?? 0],
    ["mailer snapshots", metrics.mailer_status_snapshots ?? 0],
    ["mail lessons", metrics.mail_signal_lessons ?? 0],
    ["clean recoveries", metrics.clean_window_recovery_runs ?? 0],
    ["clean rechecks", metrics.clean_window_recheck_runs ?? 0],
    ["post-window checks", metrics.post_window_recheck_runs ?? 0],
    ["customer journeys", metrics.customer_journey_snapshots ?? 0],
    ["customer tokens", metrics.customer_access_tokens ?? 0],
    ["monitoring runs", metrics.monitoring_runs ?? 0],
    ["scout checks", metrics.scout_self_checks ?? 0],
    ["scout provenance", metrics.scout_provenance_scores ?? 0],
    ["audit strength", metrics.audit_strength_scores ?? 0],
    ["language gates", metrics.public_language_gate_runs ?? 0],
  ];

  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue Admin</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="dashboard">
        <aside className="sidebar">
          <div className="eyebrow">Control room</div>
          <div className="actions tight">
            <a className="button primary" href="/admin">Open pipeline</a>
            <a className="button secondary" href="/r/demo">View audit</a>
          </div>
          <h1 style={{fontSize: 34, lineHeight: 1.05}}>Pipeline is gated</h1>
          <p className="lede" style={{fontSize: 15}}>Live sends, warmup, auto-replies, and Paddle customer-facing provisioning stay paused until P0 gates pass.</p>
        </aside>
        <section className="content">
          <div className="metric-grid">
            {cards.map(([value, label]) => <div className="metric" key={label}><strong>{value}</strong><span>{label}</span></div>)}
          </div>
          <div className="panel">
            <h2>Scanner Jobs</h2>
            {["queued", "running", "completed", "failed"].map((item) => (
              <div className="row" key={item}><span className="tag">{item}</span><span>scan jobs</span><span className="score">{scans[item] ?? 0}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Outreach Queue</h2>
            {["queued", "sent", "bounced", "replied"].map((item) => (
              <div className="row" key={item}><span className="tag">{item}</span><span>messages</span><span className="score">{emails[item] ?? 0}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Kill Switches</h2>
            {Object.entries(switches).map(([key, value]) => (
              <div className="row" key={key}><span className="tag">{value ? "on" : "off"}</span><span>{key.replaceAll("_", " ")}</span><span className="score">{value ? "blocked" : "armed"}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Owner Commands</h2>
            <div className="row"><span className="tag">stored</span><span>gated inbox commands</span><span className="score">{metrics.owner_commands ?? 0}</span></div>
            <div className="row"><span className="tag">visual</span><span>QA runs</span><span className="score">{metrics.visual_qa_runs ?? 0}</span></div>
            <div className="row"><span className="tag">mail</span><span>QA runs</span><span className="score">{metrics.mail_qa_runs ?? 0}</span></div>
          </div>
          <div className="panel">
            <h2>Mailer Control</h2>
            <div className="row"><span className="tag">status</span><span>latest autonomous mailer state</span><span className="score">{latestMailer.status ?? "unknown"}</span></div>
            <div className="row"><span className="tag">next</span><span>safe mail action</span><span className="score">{latestMailer.next_safe_action ?? "wait"}</span></div>
            <div className="row"><span className="tag">send</span><span>live outreach gate</span><span className="score">blocked</span></div>
          </div>
          <div className="panel">
            <h2>Mailer Autonomy</h2>
            <div className="row"><span className="tag">qa</span><span>latest mail QA</span><span className="score">{mailer.latest_snapshot?.mail_qa_decision ?? metrics.latest_mailer_status?.mail_qa_decision ?? "unknown"}</span></div>
            <div className="row"><span className="tag">bounce</span><span>recent bounce or DSN signals</span><span className="score">{mailerSignals.bounce_or_dsn_count ?? 0}</span></div>
            <div className="row"><span className="tag">limit</span><span>recent SMTP rate-limit signals</span><span className="score">{mailerSignals.rate_limit_count ?? 0}</span></div>
            <div className="row"><span className="tag">next</span><span>autonomous next action</span><span className="score">{mailer.next_allowed_action ?? "wait"}</span></div>
            <div className="row"><span className="tag">warmup</span><span>warmup gate</span><span className="score">{mailer.warmup_allowed ? "armed" : "blocked"}</span></div>
            <div className="row"><span className="tag">clean</span><span>latest clean-window recovery</span><span className="score">{cleanRecovery.status ?? "not run"}</span></div>
          </div>
          <div className="panel">
            <h2>Mailer Ledger</h2>
            <div className="row"><span className="tag">policy</span><span>all mail input and output</span><span className="score">gated</span></div>
            <div className="row"><span className="tag">owner</span><span>stored owner commands</span><span className="score">{ledgerOwner.total ?? 0}</span></div>
            <div className="row"><span className="tag">inbox</span><span>human-review threads</span><span className="score">{ledgerInbound.human_review_required ?? 0}</span></div>
            <div className="row"><span className="tag">send</span><span>live outreach from ledger</span><span className="score">{ledgerGates.live_outreach_allowed ? "armed" : "blocked"}</span></div>
            <div className="row"><span className="tag">reply</span><span>auto-replies</span><span className="score">{ledgerGates.auto_replies_allowed ? "armed" : "paused"}</span></div>
            <div className="row"><span className="tag">throttle</span><span>active throttle states</span><span className="score">{ledgerThrottle.states ?? 0}</span></div>
            <div className="row"><span className="tag">backoff</span><span>active mail backoffs</span><span className="score">{ledgerThrottle.backoff_active ?? 0}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw addresses in admin payload</span><span className="score">{ledger.privacy?.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">blockers</span><span>current mailer gate blockers</span><span className="score">{Array.isArray(ledgerGates.blockers) ? ledgerGates.blockers.length : 0}</span></div>
            <div className="row"><span className="tag">outbound</span><span>outbound status groups</span><span className="score">{Array.isArray(ledgerOutbound.messages_by_status) ? ledgerOutbound.messages_by_status.length : 0}</span></div>
          </div>
          <div className="panel">
            <h2>Mailer Action Queue</h2>
            <div className="row"><span className="tag">queued</span><span>prepared mail actions waiting for gates</span><span className="score">{actionQueue.queued ?? 0}</span></div>
            <div className="row"><span className="tag">prepared</span><span>safe actions prepared without sending</span><span className="score">{actionQueue.prepared ?? 0}</span></div>
            <div className="row"><span className="tag">ready</span><span>customer mail send-ready evidence</span><span className="score">{actionQueue.send_ready ?? 0}</span></div>
            <div className="row"><span className="tag">blocked</span><span>actions blocked by safety gates</span><span className="score">{actionQueue.blocked ?? 0}</span></div>
            <div className="row"><span className="tag">sent</span><span>actions sent by this router</span><span className="score">{actionQueue.sent ?? 0}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw addresses in queue payload</span><span className="score">{actionQueue.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">send</span><span>router send capability</span><span className="score">{actionQueue.send_mail ? "armed" : "evidence only"}</span></div>
            <div className="row"><span className="tag">blockers</span><span>current ledger blockers</span><span className="score">{Array.isArray(actionQueue.ledger_blockers) ? actionQueue.ledger_blockers.length : 0}</span></div>
            {customerMailCounts.length ? customerMailCounts.slice(0, 5).map((item: any) => (
              <div className="row" key={`${item.action_type}-${item.status}`}><span className="tag">{item.status}</span><span>{String(item.action_type).replaceAll("_", " ")}</span><span className="score">{item.count}</span></div>
            )) : <div className="row"><span className="tag">customer</span><span>customer mail actions</span><span className="score">0</span></div>}
          </div>
          <div className="panel">
            <h2>Customer Mail Gate</h2>
            <div className="row"><span className="tag">sim</span><span>customer mail simulation cases</span><span className="score">{simulation.case_count ?? 0}</span></div>
            <div className="row"><span className="tag">products</span><span>paid products covered</span><span className="score">{simulation.product_count ?? 0}</span></div>
            <div className="row"><span className="tag">failures</span><span>simulation blocking failures</span><span className="score">{simulation.blocking_failures ?? 0}</span></div>
            <div className="row"><span className="tag">resolver</span><span>recipient resolver audit rows</span><span className="score">{closedLoop.resolver_audit?.total ?? 0}</span></div>
            <div className="row"><span className="tag">ledger</span><span>customer mail send ledger rows</span><span className="score">{sendLedger.total ?? 0}</span></div>
            <div className="row"><span className="tag">blocked</span><span>transport-blocked customer sends</span><span className="score">{sendLedger.transport_blocked ?? sendLedger.blocked ?? 0}</span></div>
            <div className="row"><span className="tag">failed</span><span>failed customer transport attempts</span><span className="score">{sendLedger.failed ?? 0}</span></div>
            <div className="row"><span className="tag">signals</span><span>recent bounce or rate-limit blockers</span><span className="score">{(closedLoopSignals.bounce_or_dsn_count ?? 0) + (closedLoopSignals.rate_limit_count ?? 0)}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in admin summaries</span><span className="score">{closedLoop.raw_recipient_addresses_included || simulation.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">send</span><span>real customer SMTP</span><span className="score">{simulation.real_smtp_called ? "called" : "off"}</span></div>
          </div>
          <div className="panel">
            <h2>Mailer Ops Controls</h2>
            <div className="ops-grid">
              <form action={runMailerOpsAction}>
                <input type="hidden" name="action" value="customer_simulation" />
                <input type="hidden" name="limit" value="10" />
                <button className="button secondary" type="submit">Run simulation</button>
              </form>
              <form action={runMailerOpsAction}>
                <input type="hidden" name="action" value="closed_loop_dry_run" />
                <input type="hidden" name="limit" value="10" />
                <button className="button secondary" type="submit">Closed-loop dry run</button>
              </form>
              <form action={runMailerOpsAction}>
                <input type="hidden" name="action" value="customer_transport_dry_run" />
                <input type="hidden" name="limit" value="10" />
                <button className="button secondary" type="submit">Transport dry run</button>
              </form>
              <form action={runMailerOpsAction}>
                <input type="hidden" name="action" value="owner_report_action" />
                <input type="hidden" name="limit" value="1" />
                <button className="button secondary" type="submit">Prepare owner report</button>
              </form>
              <form action={runMailerOpsAction}>
                <input type="hidden" name="action" value="digest_history_cleanup" />
                <input type="hidden" name="limit" value="1" />
                <button className="button secondary" type="submit">Digest cleanup</button>
              </form>
            </div>
            <div className="row"><span className="tag">latest</span><span>recorded ops actions</span><span className="score">{opsActions.count ?? 0}</span></div>
            <div className="row"><span className="tag">real</span><span>real ops action history</span><span className="score">{opsActions.real_count ?? 0}</span></div>
            <div className="row"><span className="tag">test</span><span>synthetic ops action history</span><span className="score">{opsActions.synthetic_count ?? 0}</span></div>
            <div className="row"><span className="tag">retained</span><span>synthetic ops rows retained</span><span className="score">{opsActions.synthetic_count ?? 0}</span></div>
            <div className="row"><span className="tag">real</span><span>latest retained real ops action</span><span className="score">{latestRealOpsAction.action ? String(latestRealOpsAction.action).replaceAll("_", " ") : "none"}</span></div>
            <div className="row"><span className="tag">agent</span><span>mailer ops retention agent status</span><span className="score">{opsRetentionAgent.status ?? "not run"}</span></div>
            <div className="row"><span className="tag">agent</span><span>retention agent runs</span><span className="score">{opsActions.retention_agent_runs ?? 0}</span></div>
            <div className="row"><span className="tag">deleted</span><span>latest synthetic ops cleanup count</span><span className="score">{opsRetentionAgent.deleted_count ?? 0}</span></div>
            <div className="row"><span className="tag">kept</span><span>latest retained real ops count</span><span className="score">{opsRetentionAgent.retained_real_count ?? 0}</span></div>
            <div className="row"><span className="tag">report</span><span>ops retention runtime report</span><span className="score">{opsRetentionReport.exists ? "written" : "missing"}</span></div>
            <div className="row"><span className="tag">path</span><span>ops retention report location</span><span className="score">{opsRetentionReport.path_stored ? "stored" : "none"}</span></div>
            <div className="row"><span className="tag">time</span><span>ops retention report last updated</span><span className="score">{opsRetentionReport.modified_at ? new Date(opsRetentionReport.modified_at).toLocaleString("en-GB") : "not yet"}</span></div>
            <div className="row"><span className="tag">history</span><span>ops retention history rows</span><span className="score">{opsRetentionHistory.count ?? 0}</span></div>
            <div className="row"><span className="tag">latest</span><span>latest retention history no-send state</span><span className="score">{latestOpsRetentionHistory.send_mail ? "send" : "no-send"}</span></div>
            <div className="row"><span className="tag">kept</span><span>latest history retained real count</span><span className="score">{latestOpsRetentionHistory.retained_real_count ?? 0}</span></div>
            <div className="row"><span className="tag">blocked</span><span>unsafe ops actions blocked</span><span className="score">{opsActions.blocked_unsafe_count ?? 0}</span></div>
            <div className="row"><span className="tag">send</span><span>ops action SMTP capability</span><span className="score">{opsActions.send_mail ? "armed" : "no-send"}</span></div>
            <div className="row"><span className="tag">agent send</span><span>retention agent SMTP capability</span><span className="score">{opsRetentionAgent.send_mail ? "armed" : "no-send"}</span></div>
            <div className="row"><span className="tag">report send</span><span>retention report SMTP capability</span><span className="score">{opsRetentionReport.send_mail ? "armed" : "no-send"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in ops action summaries</span><span className="score">{opsActions.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in retention agent summary</span><span className="score">{opsRetentionAgent.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in retention report metadata</span><span className="score">{opsRetentionReport.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in retention history</span><span className="score">{opsRetentionHistory.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">secret</span><span>secrets in retention history</span><span className="score">{opsRetentionHistory.secrets_included ? "blocked" : "omitted"}</span></div>
            {Array.isArray(opsActions.latest) && opsActions.latest.length ? opsActions.latest.slice(0, 3).map((item: any) => (
              <div className="row" key={item.id}><span className="tag">{item.is_synthetic ? "test" : item.status}</span><span>{String(item.action).replaceAll("_", " ")}</span><span className="score">{item.send_mail ? "send" : "no-send"}</span></div>
            )) : <div className="row"><span className="tag">idle</span><span>no ops actions recorded yet</span><span className="score">0</span></div>}
          </div>
          <div className="panel">
            <h2>Daily Digest Evidence</h2>
            <div className="row"><span className="tag">draft</span><span>daily digest owner report action status</span><span className="score">{digest.owner_report_action_status ?? "none"}</span></div>
            <div className="row"><span className="tag">real</span><span>mailer ops real count in digest</span><span className="score">{digestOps.real_count ?? 0}</span></div>
            <div className="row"><span className="tag">test</span><span>mailer ops synthetic count in digest</span><span className="score">{digestOps.synthetic_count ?? 0}</span></div>
            <div className="row"><span className="tag">blocked</span><span>blocked unsafe ops count in digest</span><span className="score">{digestOps.blocked_unsafe_count ?? 0}</span></div>
            <div className="row"><span className="tag">latest</span><span>latest owner report generated state</span><span className="score">{digest.latest_owner_report ? "generated" : "none"}</span></div>
            <div className="row"><span className="tag">agent</span><span>digest agent runtime report</span><span className="score">{digestReport.exists ? "written" : "missing"}</span></div>
            <div className="row"><span className="tag">path</span><span>digest runtime report location</span><span className="score">{digestReport.path ? "stored" : "none"}</span></div>
            <div className="row"><span className="tag">time</span><span>digest report last updated</span><span className="score">{digestReport.modified_at ? new Date(digestReport.modified_at).toLocaleString("en-GB") : "not yet"}</span></div>
            <div className="row"><span className="tag">history</span><span>digest report history rows</span><span className="score">{digestHistory.count ?? 0}</span></div>
            <div className="row"><span className="tag">latest</span><span>latest digest history no-send state</span><span className="score">{latestDigestHistory.email_sent ? "sent" : "no-send"}</span></div>
            <div className="row"><span className="tag">ops</span><span>ops retention history rows</span><span className="score">{digestOpsRetentionHistory.count ?? 0}</span></div>
            <div className="row"><span className="tag">latest</span><span>latest ops retention no-send state</span><span className="score">{latestDigestOpsRetentionHistory.send_mail ? "send" : "no-send"}</span></div>
            <div className="row"><span className="tag">kept</span><span>latest ops retention retained real</span><span className="score">{latestDigestOpsRetentionHistory.retained_real_count ?? 0}</span></div>
            <div className="row"><span className="tag">send</span><span>daily digest email send state</span><span className="score">{digest.email_sent ? "sent" : "no-send"}</span></div>
            <div className="row"><span className="tag">agent send</span><span>digest agent transport state</span><span className="score">{digestReport.email_sent ? "sent" : "no-send"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in digest summary</span><span className="score">{digest.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in digest report metadata</span><span className="score">{digestReport.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in digest history</span><span className="score">{digestHistory.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in ops retention history</span><span className="score">{digestOpsRetentionHistory.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">secret</span><span>secrets in ops retention history</span><span className="score">{digestOpsRetentionHistory.secrets_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">guard</span><span>latest trend guard decision</span><span className="score">{trendGuard.decision ?? "unknown"}</span></div>
            <div className="row"><span className="tag">guard</span><span>latest trend guard regressions</span><span className="score">{trendGuard.regression_count ?? 0}</span></div>
            <div className="row"><span className="tag">queue</span><span>trend guard action queue rows</span><span className="score">{trendQueue.mailer_action_queue_rows ?? 0}</span></div>
            <div className="row"><span className="tag">ledger</span><span>trend guard send ledger rows</span><span className="score">{trendQueue.mailer_send_ledger_rows ?? 0}</span></div>
            <div className="row"><span className="tag">resolver</span><span>trend guard resolver audit rows</span><span className="score">{trendQueue.recipient_resolver_audit_rows ?? 0}</span></div>
            <div className="row"><span className="tag">time</span><span>trend guard latest run</span><span className="score">{trendGuard.latest_run_completed_at ? new Date(trendGuard.latest_run_completed_at).toLocaleString("en-GB") : "not yet"}</span></div>
            <div className="row"><span className="tag">send</span><span>trend guard SMTP capability</span><span className="score">{trendGuard.send_mail ? "armed" : "no-send"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw history rows in trend guard</span><span className="score">{trendGuard.raw_history_rows_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">secret</span><span>secrets in trend guard summary</span><span className="score">{trendGuard.secrets_included ? "blocked" : "omitted"}</span></div>
          </div>
          <div className="panel">
            <h2>Clean Window Recheck</h2>
            <div className="row"><span className="tag">{recheck.signal_window_clear ? "clear" : "blocked"}</span><span>mail signal window</span><span className="score">{recheck.signal_window_clear ? "ready" : "waiting"}</span></div>
            <div className="row"><span className="tag">safe at</span><span>next possible recheck time</span><span className="score">{recheck.next_safe_at ? new Date(recheck.next_safe_at).toLocaleString("en-GB") : "now"}</span></div>
            <div className="row"><span className="tag">qa</span><span>mail QA before resume</span><span className="score">{recheck.mail_qa_decision ?? "unknown"}</span></div>
            <div className="row"><span className="tag">send</span><span>live outreach gate</span><span className="score">blocked</span></div>
          </div>
          <div className="panel">
            <h2>Post-Window Transition</h2>
            <div className="row"><span className="tag">{postWindow.recheck_due ? "due" : "wait"}</span><span>scheduled no-send recheck</span><span className="score">{postWindow.recheck_due ? "ready" : "not due"}</span></div>
            <div className="row"><span className="tag">safe at</span><span>transition recheck time</span><span className="score">{postWindow.next_safe_at ? new Date(postWindow.next_safe_at).toLocaleString("en-GB") : "now"}</span></div>
            <div className="row"><span className="tag">decision</span><span>warmup-ready transition</span><span className="score">{postWindow.transition_decision ?? "NOT_RUN"}</span></div>
            <div className="row"><span className="tag">send</span><span>manual send forcing</span><span className="score">disabled</span></div>
          </div>
          <div className="panel">
            <h2>Mail Signal Lessons</h2>
            {mailerLessons.length ? mailerLessons.slice(0, 5).map((lesson: any) => (
              <div className="row" key={lesson.lesson_key}><span className="tag">{lesson.severity}</span><span>{lesson.signal_type}</span><span className="score">active</span></div>
            )) : <div className="row"><span className="tag">clear</span><span>no active lessons recorded</span><span className="score">0</span></div>}
          </div>
          <div className="panel">
            <h2>Monitoring Control</h2>
            <div className="row"><span className="tag">due</span><span>targets due for safe check</span><span className="score">{monitoring.due_now ?? 0}</span></div>
            <div className="row"><span className="tag">runs</span><span>latest monitoring runs shown</span><span className="score">{monitoringRuns.length}</span></div>
            <div className="row"><span className="tag">policy</span><span>customer site changes</span><span className="score">blocked</span></div>
            {monitoringStatuses.length ? monitoringStatuses.map((item: any) => (
              <div className="row" key={item.status}><span className="tag">{item.status}</span><span>monitoring targets</span><span className="score">{item.count}</span></div>
            )) : <div className="row"><span className="tag">none</span><span>monitoring targets</span><span className="score">0</span></div>}
          </div>
          <div className="panel">
            <h2>Warmup Calendar Evidence</h2>
            <div className="row"><span className="tag">scheduled</span><span>warmup messages planned</span><span className="score">{mailerWarmup.scheduled_total ?? 0}</span></div>
            <div className="row"><span className="tag">due</span><span>warmup due now</span><span className="score">{mailerWarmup.due_now ?? 0}</span></div>
            <div className="row"><span className="tag">sent</span><span>warmup sent today</span><span className="score">{mailerWarmup.sent_today ?? 0}</span></div>
            <div className="row"><span className="tag">blocked</span><span>warmup blocked today</span><span className="score">{mailerWarmup.blocked_today ?? 0}</span></div>
          </div>
          <div className="panel">
            <h2>Autonomous Agents</h2>
            {ops.map(([label, value]) => (
              <div className="row" key={String(label)}><span className="tag">agent</span><span>{String(label)}</span><span className="score">{String(value)}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Self-Operating Engine</h2>
            {selfOps.map(([label, value]) => (
              <div className="row" key={String(label)}><span className="tag">self</span><span>{String(label)}</span><span className="score">{String(value)}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Launch Pools</h2>
            <div className="row"><span className="tag">warmup</span><span>approved recipient pool</span><span className="score">{metrics.warmup_recipients ?? 0}</span></div>
            <div className="row"><span className="tag">test</span><span>approved deliverability inboxes</span><span className="score">{metrics.test_inboxes ?? 0}</span></div>
            <div className="row"><span className="tag">preview</span><span>outreach preview batches</span><span className="score">{metrics.outreach_preview_batches ?? 0}</span></div>
          </div>
        </section>
      </main>
    </div>
  );
}
