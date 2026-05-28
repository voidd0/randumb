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

  async function runCampaignAction(formData: FormData) {
    "use server";
    const action = String(formData.get("action") || "");
    const campaign_id = String(formData.get("campaign_id") || "") || undefined;
    const limit = Number(formData.get("limit") || 25);
    const dry_run = String(formData.get("dry_run") || "false") === "true";
    await postJson("/admin/campaign-actions/run", { action, campaign_id, limit, dry_run });
  }

  async function reviewCampaignPreview(formData: FormData) {
    "use server";
    const campaign_lead_id = String(formData.get("campaign_lead_id") || "");
    const action = String(formData.get("review_action") || "held");
    const reason = String(formData.get("reason") || "");
    await postJson("/admin/campaign-control-room/review", { campaign_lead_id, action, reason, actor: "admin" });
  }

  async function autoReviewCampaignPreviews(formData: FormData) {
    "use server";
    const limit = Number(formData.get("limit") || 20);
    const apply = String(formData.get("apply") || "true") === "true";
    await postJson("/admin/campaign-control-room/auto-review", { limit, apply });
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
  const simulationData = await fetchJson("/admin/mailer/customer-simulation", authorization ? { Authorization: authorization } : {});
  const opsActionData = await fetchJson("/admin/mailer/ops-actions", authorization ? { Authorization: authorization } : {});
  const opsRetentionHistoryData = await fetchJson("/admin/mailer/ops-retention-history", authorization ? { Authorization: authorization } : {});
  const digestData = await fetchJson("/admin/mailer/digest-summary", authorization ? { Authorization: authorization } : {});
  const trendGuardData = await fetchJson("/admin/mailer/digest-trend-guard/latest", authorization ? { Authorization: authorization } : {});
  const policyScoreData = await fetchJson("/admin/mailer/policy-score", authorization ? { Authorization: authorization } : {});
  const policyScoreHistoryData = await fetchJson("/admin/mailer/policy-score/history", authorization ? { Authorization: authorization } : {});
  const policyScoreRetentionData = await fetchJson("/admin/mailer/policy-score/retention", authorization ? { Authorization: authorization } : {});
  const policyScoreRegressionData = await fetchJson("/admin/mailer/policy-score/regression-guard/latest", authorization ? { Authorization: authorization } : {});
  const scoutQualitySummaryData = await fetchJson("/admin/scouts/campaign-quality-summary", authorization ? { Authorization: authorization } : {});
  const scoutQualityHistoryData = await fetchJson("/admin/scouts/campaign-quality-history", authorization ? { Authorization: authorization } : {});
  const scoutSourceReadinessData = await fetchJson("/admin/scouts/source-readiness-summary", authorization ? { Authorization: authorization } : {});
  const scoutSourceReadinessGuardData = await fetchJson("/admin/scouts/source-readiness-regression-guard/latest", authorization ? { Authorization: authorization } : {});
  const campaignControlRoomData = await fetchJson("/admin/campaign-control-room?limit=25&threshold=70", authorization ? { Authorization: authorization } : {});
  const campaignActionsData = await fetchJson("/admin/campaign-actions?limit=8", authorization ? { Authorization: authorization } : {});
  const launchReadinessData = await fetchJson("/admin/launch-readiness-scoreboard?limit=25", authorization ? { Authorization: authorization } : {});
  const launchActivationData = await fetchJson("/admin/launch-activation?limit=25", authorization ? { Authorization: authorization } : {});
  const launchRunbookData = await fetchJson("/admin/launch-activation/runbook?limit=25", authorization ? { Authorization: authorization } : {});
  const launchRehearsalData = await fetchJson("/admin/launch-rehearsal?limit=5", authorization ? { Authorization: authorization } : {});
  const liveQueueData = await fetchJson("/admin/outreach/live-queue?limit=20", authorization ? { Authorization: authorization } : {});
  const postSendObserverData = await fetchJson("/admin/outreach/post-send-observer?limit=5", authorization ? { Authorization: authorization } : {});
  const studioMailData = await fetchJson("/admin/studio-mail/messages?limit=8", authorization ? { Authorization: authorization } : {});
  const studioMailRunsData = await fetchJson("/admin/studio-mail/runs?limit=5", authorization ? { Authorization: authorization } : {});
  const monitoringData = await fetchJson("/admin/monitoring/summary", authorization ? { Authorization: authorization } : {});
  const paidCustomerWatchdogData = await fetchJson("/admin/customers/revenue-watchdog?limit=5", authorization ? { Authorization: authorization } : {});
  const selfClosedLoopData = await fetchJson("/admin/self/closed-loop?limit=5", authorization ? { Authorization: authorization } : {});
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
  const policyScore = policyScoreData?.policy_score || {};
  const policyQueue = policyScore.queue_hygiene || {};
  const policyScoreHistory = policyScoreHistoryData?.history || digest.mailer_policy_score_history || {};
  const policyScoreRetention = policyScoreRetentionData?.retention || {};
  const policyScoreRegression = policyScoreRegressionData?.guard || {};
  const scoutQualitySummary = scoutQualitySummaryData?.summary || {};
  const scoutRunStatuses = scoutQualitySummary.scout_runs_by_status || {};
  const scoutLatestSelfCheck = scoutQualitySummary.latest_self_check || {};
  const scoutLatestProvenance = scoutQualitySummary.latest_provenance || {};
  const scoutCampaignQuality = scoutQualitySummary.campaign_quality || {};
  const scoutQualityHistory = scoutQualityHistoryData?.history || {};
  const latestScoutQualityHistory = scoutQualityHistory.latest || {};
  const latestScoutQualityCampaign = latestScoutQualityHistory.campaign_quality_json || {};
  const scoutSourceReadiness = scoutSourceReadinessData?.summary || {};
  const scoutSourceReadinessLatest = Array.isArray(scoutSourceReadiness.latest) ? scoutSourceReadiness.latest[0] || {} : {};
  const scoutSourceReadinessGuard = scoutSourceReadinessGuardData?.guard || scoutSourceReadiness.regression_guard || {};
  const campaignControlRoom = campaignControlRoomData?.control_room || {};
  const campaignActions = campaignActionsData?.actions || {};
  const campaignActionRuns = Array.isArray(campaignActions.latest_runs) ? campaignActions.latest_runs : [];
  const campaignActionCampaigns = Array.isArray(campaignActions.campaigns) ? campaignActions.campaigns : [];
  const campaignSegments = Array.isArray(campaignControlRoom.top_segments) ? campaignControlRoom.top_segments : [];
  const campaignPreviewRows = Array.isArray(campaignControlRoom.first_batch_preview_rows) ? campaignControlRoom.first_batch_preview_rows : [];
  const launchReadiness = launchReadinessData?.scoreboard || {};
  const launchActivation = launchActivationData?.activation || {};
  const launchRunbook = launchRunbookData?.runbook || {};
  const launchRehearsal = launchRehearsalData?.history || {};
  const latestLaunchRehearsalRun = Array.isArray(launchRehearsal.runs) ? launchRehearsal.runs[0] || {} : {};
  const launchActivationHistory = launchActivationData?.history || {};
  const latestLaunchActivationRun = Array.isArray(launchActivationHistory.runs) ? launchActivationHistory.runs[0] || {} : {};
  const liveQueue = liveQueueData?.candidates || {};
  const liveQueueHistory = liveQueueData?.history || {};
  const latestLiveQueueRun = Array.isArray(liveQueueHistory.runs) ? liveQueueHistory.runs[0] || {} : {};
  const postSendObserver = postSendObserverData?.history || {};
  const latestPostSendObserverRun = Array.isArray(postSendObserver.runs) ? postSendObserver.runs[0] || {} : {};
  const paidCustomerWatchdog = paidCustomerWatchdogData?.history || {};
  const latestPaidCustomerWatchdogRun = Array.isArray(paidCustomerWatchdog.runs) ? paidCustomerWatchdog.runs[0] || {} : {};
  const launchEvidence = launchReadiness.evidence || {};
  const launchMail = launchEvidence.mail || {};
  const launchVisual = launchEvidence.visual || {};
  const launchTransport = launchEvidence.transport_gate || {};
  const launchTransportChecks = launchTransport.checks || {};
  const launchWarmupMaturity = launchEvidence.warmup_maturity || {};
  const launchCampaigns = launchEvidence.campaigns || {};
  const studioMail = studioMailData?.studio_mail || {};
  const studioMailMessages = Array.isArray(studioMail.messages) ? studioMail.messages : [];
  const studioMailRuns = studioMailRunsData?.runs || {};
  const latestStudioMailRun = Array.isArray(studioMailRuns.runs) ? studioMailRuns.runs[0] || {} : {};
  const selfClosedLoop = selfClosedLoopData || {};
  const selfCycles = Array.isArray(selfClosedLoop.cycles) ? selfClosedLoop.cycles : [];
  const latestSelfCycle = selfCycles[0] || {};
  const latestSelfCycleResult = latestSelfCycle.result_json || {};
  const latestRealOpsAction = opsActions.latest_real || {};
  const opsRetentionAgent = opsActions.latest_retention_agent || {};
  const opsRetentionReport = opsActions.retention_agent_report || {};
  const monitoring = monitoringData?.summary || {};
  const cards = Object.entries(labels).map(([key, label]) => [String(metrics[key] ?? 0), label]);
  const scans = metrics.scans || {};
  const emails = metrics.emails || {};
  const production = metrics.production || {};
  const qaArtifacts = metrics.qa_artifacts || {};
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
    ["closed loops", metrics.self_operating_cycles ?? 0],
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
    ["scout quality history", metrics.scout_campaign_quality_history ?? 0],
    ["audit strength", metrics.audit_strength_scores ?? 0],
    ["language gates", metrics.public_language_gate_runs ?? 0],
    ["campaign actions", metrics.campaign_action_runs ?? 0],
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
            <h2>Production Metrics</h2>
            <div className="segment-grid">
              <div className="segment-card">
                <span className="tag">real</span>
                <strong>{production.real_leads_total ?? 0}</strong>
                <span>non-test leads</span>
              </div>
              <div className="segment-card">
                <span className="tag">qualified</span>
                <strong>{production.real_qualified_leads ?? 0}</strong>
                <span>real scored leads</span>
              </div>
              <div className="segment-card">
                <span className="tag">audits</span>
                <strong>{production.real_audit_pages_generated ?? 0}</strong>
                <span>public real audit pages</span>
              </div>
              <div className="segment-card">
                <span className="tag">preview</span>
                <strong>{production.real_campaign_preview_rows ?? 0}</strong>
                <span>real no-send campaign rows</span>
              </div>
            </div>
            <div className="segments-list">
              <div className="segment-row">
                <span className="readiness-chip">qa separated</span>
                <strong>Runtime test artifacts</strong>
                <span>{qaArtifacts.test_like_businesses ?? 0} businesses</span>
                <span>{qaArtifacts.test_like_audits ?? 0} audits</span>
                <span>{qaArtifacts.test_like_campaign_previews ?? 0} previews</span>
              </div>
            </div>
          </div>
          <div className="panel readiness-panel">
            <div>
              <div className="eyebrow">Revenue launch gate</div>
              <h2>Real campaign previews are ready, sending is still locked</h2>
              <p className="muted">The control room has proof-backed candidates, but the transport gate stays closed until the explicit live-send flags are changed and the mailer remains clean.</p>
            </div>
            <div className="readiness-score">
              <strong>{launchReadiness.score ?? 0}</strong>
              <span>{launchReadiness.state ?? "unknown"}</span>
            </div>
            <div className="segment-grid">
              <div className="segment-card">
                <span className="tag">campaigns</span>
                <strong>{launchCampaigns.ready_candidate_count ?? campaignControlRoom.ready_candidate_count ?? 0}/{launchCampaigns.candidate_count ?? campaignControlRoom.candidate_count ?? 0}</strong>
                <span>ready preview candidates</span>
              </div>
              <div className="segment-card">
                <span className="tag">mail</span>
                <strong>{launchMail.mail_qa_decision ?? campaignControlRoom.mail_qa_decision ?? "unknown"}</strong>
                <span>strict auth and signal gate</span>
              </div>
              <div className="segment-card">
                <span className="tag">visual</span>
                <strong>{launchVisual.visual_qa_decision ?? "unknown"}</strong>
                <span>Huanshu plus {launchVisual.additional_tool_count ?? 0} plugins</span>
              </div>
              <div className="segment-card">
                <span className="tag">send</span>
                <strong>{launchReadiness.live_outreach_allowed ? "armed" : "blocked"}</strong>
                <span>{launchTransport.reason ?? "no live-send approval"}</span>
              </div>
              <div className="segment-card">
                <span className="tag">warmup</span>
                <strong>{launchWarmupMaturity.allowed ? "verified" : "waiting"}</strong>
                <span>{launchWarmupMaturity.warmup_sent_count ?? 0}/{launchWarmupMaturity.min_clean_sends_required ?? 5} clean sends</span>
              </div>
              <div className="segment-card">
                <span className="tag">unsubscribe</span>
                <strong>{launchTransportChecks.unsubscribe_one_click_ready ? "ready" : "blocked"}</strong>
                <span>one-click signed link</span>
              </div>
              <div className="segment-card">
                <span className="tag">html</span>
                <strong>{launchTransportChecks.html_body_ready ? "ready" : "blocked"}</strong>
                <span>branded multipart body</span>
              </div>
              <div className="segment-card">
                <span className="tag">launch flags</span>
                <strong>{launchTransportChecks.outreach_dry_run || launchTransportChecks.outreach_paused || !launchTransportChecks.first_live_send_flag ? "locked" : "armed"}</strong>
                <span>dry-run {launchTransportChecks.outreach_dry_run ? "on" : "off"} · pause {launchTransportChecks.outreach_paused ? "on" : "off"}</span>
              </div>
              <div className="segment-card">
                <span className="tag">activation</span>
                <strong>{launchActivation.decision ?? "checking"}</strong>
                <span>{(launchActivation.blockers || []).length ?? 0} blockers · latest {latestLaunchActivationRun.decision ?? "none"}</span>
              </div>
              <div className="segment-card">
                <span className="tag">first day</span>
                <strong>{launchActivation.quota?.daily_sent ?? launchTransportChecks.live_quota?.daily_sent ?? 0}/{launchActivation.quota?.daily_limit ?? launchTransportChecks.live_quota?.daily_limit ?? 20}</strong>
                <span>live sends remain locked</span>
              </div>
              <div className="segment-card">
                <span className="tag">canary queue</span>
                <strong>{liveQueue.candidate_count ?? 0}</strong>
                <span>latest stage {latestLiveQueueRun.decision ?? "none"}</span>
              </div>
              <div className="segment-card">
                <span className="tag">post-send watch</span>
                <strong>{latestPostSendObserverRun.decision ?? "idle"}</strong>
                <span>bounces {latestPostSendObserverRun.bounce_or_dsn_count ?? 0} · replies {latestPostSendObserverRun.reply_count ?? 0}</span>
              </div>
              <div className="segment-card">
                <span className="tag">rehearsal</span>
                <strong>{latestLaunchRehearsalRun.decision ?? "not run"}</strong>
                <span>{latestLaunchRehearsalRun.passed_step_count ?? 0}/{latestLaunchRehearsalRun.step_count ?? 0} steps</span>
              </div>
              <div className="segment-card">
                <span className="tag">paid customers</span>
                <strong>{latestPaidCustomerWatchdogRun.decision ?? "not run"}</strong>
                <span>{latestPaidCustomerWatchdogRun.checked_customer_count ?? 0} checked · {latestPaidCustomerWatchdogRun.repaired_customer_count ?? 0} repaired</span>
              </div>
            </div>
            <div className="segments-list">
              <div className="segment-row">
                <span className="readiness-chip">{launchActivation.decision ?? "not checked"}</span>
                <strong>Activation runbook</strong>
                <span>preview {launchActivation.preview_message_count ?? 0}</span>
                <span>approved {launchActivation.approved_preview_count ?? 0}</span>
                <span>sent {launchActivation.live_outreach_sent_count ?? 0}</span>
              </div>
              <div className="segment-row">
                <span className="readiness-chip">rollback</span>
                <strong>Live switch rollback</strong>
                <span>dry-run {launchRunbook.rollback_env?.OUTREACH_DRY_RUN ?? "true"}</span>
                <span>worker {launchRunbook.rollback_env?.OUTREACH_WORKER_ENABLED ?? "false"}</span>
                <span>{launchRunbook.rollback_steps?.length ?? 0} steps</span>
              </div>
              <div className="segment-row">
                <span className="readiness-chip">runbook</span>
                <strong>Canary activation plan</strong>
                <span>{launchRunbook.status ?? "unknown"}</span>
                <span>limit {launchRunbook.canary_limit ?? 20}</span>
                <span>{launchRunbook.operator_guard ?? "guarded"}</span>
              </div>
            </div>
            <div className="segments-list">
              {campaignSegments.slice(0, 6).map((segment: any) => (
                <div className="segment-row" key={`${segment.country}-${segment.language}-${segment.niche}`}>
                  <span className="readiness-chip">{segment.decision ?? "preview"}</span>
                  <strong>{segment.country} · {segment.niche}</strong>
                  <span>{segment.ready_count ?? 0}/{segment.lead_count ?? 0} ready</span>
                  <span>lead {segment.average_lead_score ?? 0}</span>
                  <span>audit {segment.average_audit_strength ?? 0}</span>
                </div>
              ))}
            </div>
            <div className="preview-table" aria-label="First batch campaign preview rows">
              {campaignPreviewRows.slice(0, 20).map((row: any) => (
                <div className="preview-row" key={row.campaign_lead_id}>
                  <div>
                    <strong>{row.business_name || row.domain}</strong>
                    <span>{row.country} · {row.language} · {row.niche}</span>
                  </div>
                  <div>
                    <span className="tag">lead</span>
                    <strong>{row.lead_score ?? 0}</strong>
                  </div>
                  <div>
                    <span className="tag">audit</span>
                    <strong>{row.audit_strength_score ?? row.audit_score ?? 0}</strong>
                  </div>
                  <div>
                    <span className="tag">gate</span>
                    <strong>{row.latest_preflight_status || "missing"}</strong>
                  </div>
                  <div>
                    <span className="tag">review</span>
                    <strong>{row.latest_review_action || "unreviewed"}</strong>
                  </div>
                  {row.audit_slug ? (
                    <a className="button secondary" href={`/r/${row.audit_slug}`}>Audit</a>
                  ) : (
                    <span className="button secondary disabled">Audit</span>
                  )}
                  <form className="preview-review-form" action={reviewCampaignPreview}>
                    <input type="hidden" name="campaign_lead_id" value={row.campaign_lead_id} />
                    <input type="text" name="reason" aria-label="Review reason" placeholder="reason" defaultValue={row.latest_review_reason || ""} />
                    <button name="review_action" value="approved" className="button secondary" type="submit">Approve</button>
                    <button name="review_action" value="held" className="button secondary" type="submit">Hold</button>
                    <button name="review_action" value="rejected" className="button secondary" type="submit">Reject</button>
                  </form>
                </div>
              ))}
            </div>
          </div>
          <div className="panel campaign-actions-panel">
            <div>
              <div className="eyebrow">Campaign operator</div>
              <h2>No-send campaign controls</h2>
              <p className="muted">These actions refresh proof-backed previews, run preview QA, and create internal owner evidence. They cannot call SMTP or unlock live outreach.</p>
            </div>
            <div className="ops-grid campaign-action-grid">
              <form action={runCampaignAction}>
                <input type="hidden" name="action" value="refresh_previews" />
                <input type="hidden" name="limit" value="25" />
                <input type="hidden" name="dry_run" value="false" />
                <button className="button secondary" type="submit">Refresh previews</button>
              </form>
              <form action={runCampaignAction}>
                <input type="hidden" name="action" value="run_quality" />
                <input type="hidden" name="limit" value="20" />
                <button className="button secondary" type="submit">Run campaign QA</button>
              </form>
              <form action={runCampaignAction}>
                <input type="hidden" name="action" value="owner_preview_report" />
                <input type="hidden" name="limit" value="25" />
                <input type="hidden" name="dry_run" value="false" />
                <button className="button secondary" type="submit">Owner preview</button>
              </form>
              <form action={runCampaignAction}>
                <input type="hidden" name="action" value="safety_lock" />
                <input type="hidden" name="campaign_id" value={campaignActionCampaigns[0]?.campaign_id || ""} />
                <input type="hidden" name="dry_run" value="true" />
                <button className="button secondary" type="submit">Dry-run safety lock</button>
              </form>
              <form action={autoReviewCampaignPreviews}>
                <input type="hidden" name="limit" value="20" />
                <input type="hidden" name="apply" value="true" />
                <button className="button secondary" type="submit">Auto-review previews</button>
              </form>
            </div>
            <div className="segment-grid">
              <div className="segment-card">
                <span className="tag">actions</span>
                <strong>{campaignActionRuns.length}</strong>
                <span>latest recorded runs</span>
              </div>
              <div className="segment-card">
                <span className="tag">previews</span>
                <strong>{campaignActions.control_room?.ready_candidate_count ?? 0}/{campaignActions.control_room?.candidate_count ?? 0}</strong>
                <span>ready campaign candidates</span>
              </div>
              <div className="segment-card">
                <span className="tag">smtp</span>
                <strong>{campaignActions.smtp_called ? "called" : "off"}</strong>
                <span>transport cannot run here</span>
              </div>
              <div className="segment-card">
                <span className="tag">live</span>
                <strong>{campaignActions.live_outreach_allowed ? "armed" : "blocked"}</strong>
                <span>cold outreach remains disabled</span>
              </div>
            </div>
            <div className="segments-list">
              {campaignActionRuns.length ? campaignActionRuns.slice(0, 5).map((item: any) => (
                <div className="segment-row campaign-action-row" key={item.id}>
                  <span className="readiness-chip">{item.status ?? "recorded"}</span>
                  <strong>{String(item.action || "action").replaceAll("_", " ")}</strong>
                  <span>{item.result?.send_mail ? "send" : "no-send"}</span>
                  <span>{item.result?.smtp_called ? "smtp" : "no smtp"}</span>
                  <span>{item.result?.live_outreach_allowed ? "live" : "locked"}</span>
                </div>
              )) : <div className="row"><span className="tag">idle</span><span>no campaign actions recorded yet</span><span className="score">0</span></div>}
            </div>
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
            <h2>Studio Mail Monitor</h2>
            <div className="row"><span className="tag">poll</span><span>latest em inbox poll</span><span className="score">{latestStudioMailRun.status ?? "unknown"}</span></div>
            <div className="row"><span className="tag">scanned</span><span>messages inspected in last poll</span><span className="score">{latestStudioMailRun.scanned_count ?? 0}</span></div>
            <div className="row"><span className="tag">commands</span><span>owner commands routed to global gate</span><span className="score">{latestStudioMailRun.owner_command_count ?? 0}</span></div>
            <div className="row"><span className="tag">review</span><span>studio mail items needing review</span><span className="score">{latestStudioMailRun.human_review_count ?? 0}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw private addresses in admin payload</span><span className="score">{studioMail.raw_private_addresses_included || studioMailRuns.raw_private_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">send</span><span>studio monitor send capability</span><span className="score">{studioMail.send_mail || studioMailRuns.send_mail ? "armed" : "read-only"}</span></div>
            {studioMailMessages.length ? studioMailMessages.slice(0, 5).map((item: any) => (
              <div className="row" key={item.id}>
                <span className="tag">{item.priority ?? "normal"}</span>
                <span>{String(item.classification || "classified").replaceAll("_", " ")}</span>
                <span className="score">{item.human_review_required ? "review" : "auto"}</span>
              </div>
            )) : <div className="row"><span className="tag">clear</span><span>no recent stored studio-mail items</span><span className="score">0</span></div>}
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
            <div className="row"><span className="tag">score</span><span>mailer policy score</span><span className="score">{policyScore.score ?? 0}</span></div>
            <div className="row"><span className="tag">policy</span><span>mailer policy decision</span><span className="score">{policyScore.decision ?? "unknown"}</span></div>
            <div className="row"><span className="tag">blockers</span><span>mailer policy blockers</span><span className="score">{Array.isArray(policyScore.blockers) ? policyScore.blockers.length : 0}</span></div>
            <div className="row"><span className="tag">next</span><span>mailer policy next action</span><span className="score">{policyScore.next_safe_action ?? "wait"}</span></div>
            <div className="row"><span className="tag">qa</span><span>policy score mail QA</span><span className="score">{policyScore.mail_qa_decision ?? "unknown"}</span></div>
            <div className="row"><span className="tag">queue</span><span>policy score queue rows</span><span className="score">{policyQueue.mailer_action_queue_rows ?? 0}</span></div>
            <div className="row"><span className="tag">send</span><span>policy score send state</span><span className="score">{policyScore.send_mail ? "send" : "no-send"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in policy score</span><span className="score">{policyScore.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">secret</span><span>secrets in policy score</span><span className="score">{policyScore.secrets_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">history</span><span>policy score history rows</span><span className="score">{policyScoreHistory.count ?? 0}</span></div>
            <div className="row"><span className="tag">latest</span><span>latest policy history score</span><span className="score">{policyScoreHistory.latest_score ?? 0}</span></div>
            <div className="row"><span className="tag">latest</span><span>latest policy history decision</span><span className="score">{policyScoreHistory.latest_decision ?? "missing"}</span></div>
            <div className="row"><span className="tag">send</span><span>latest policy history send state</span><span className="score">{policyScoreHistory.latest_send_mail ? "send" : "no-send"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in policy history</span><span className="score">{policyScoreHistory.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">secret</span><span>secrets in policy history</span><span className="score">{policyScoreHistory.secrets_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">retention</span><span>policy score retained rows</span><span className="score">{policyScoreRetention.total_rows ?? 0}</span></div>
            <div className="row"><span className="tag">retention</span><span>policy score retention send state</span><span className="score">{policyScoreRetention.latest_send_mail ? "send" : "no-send"}</span></div>
            <div className="row"><span className="tag">guard</span><span>policy score regression guard decision</span><span className="score">{policyScoreRegression.decision ?? "missing"}</span></div>
            <div className="row"><span className="tag">guard</span><span>policy score regression count</span><span className="score">{policyScoreRegression.regression_count ?? 0}</span></div>
            <div className="row"><span className="tag">guard</span><span>policy score drop</span><span className="score">{policyScoreRegression.score_drop ?? 0}</span></div>
            <div className="row"><span className="tag">review</span><span>policy score review task</span><span className="score">{policyScoreRegression.review_task_created ? "created" : "none"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in policy guard</span><span className="score">{policyScoreRegression.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">secret</span><span>secrets in policy guard</span><span className="score">{policyScoreRegression.secrets_included ? "blocked" : "omitted"}</span></div>
          </div>
          <div className="panel">
            <h2>Scout Quality Control</h2>
            <div className="row"><span className="tag">quality</span><span>latest scout quality summary</span><span className="score">{scoutQualitySummary.status ?? "missing"}</span></div>
            <div className="row"><span className="tag">runs</span><span>completed scout runs</span><span className="score">{scoutRunStatuses.completed ?? 0}</span></div>
            <div className="row"><span className="tag">review</span><span>scout runs requiring review</span><span className="score">{scoutRunStatuses.review_required ?? 0}</span></div>
            <div className="row"><span className="tag">self</span><span>latest scout self-check</span><span className="score">{scoutLatestSelfCheck.status ?? "missing"}</span></div>
            <div className="row"><span className="tag">accepted</span><span>latest self-check accepted leads</span><span className="score">{scoutLatestSelfCheck.accepted_count ?? 0}</span></div>
            <div className="row"><span className="tag">rejected</span><span>latest self-check rejected leads</span><span className="score">{scoutLatestSelfCheck.rejected_count ?? 0}</span></div>
            <div className="row"><span className="tag">prov</span><span>latest provenance status</span><span className="score">{scoutLatestProvenance.status ?? "missing"}</span></div>
            <div className="row"><span className="tag">score</span><span>latest provenance score</span><span className="score">{scoutLatestProvenance.score ?? 0}</span></div>
            <div className="row"><span className="tag">source</span><span>source URL coverage</span><span className="score">{Math.round(Number(scoutLatestProvenance.source_url_coverage ?? 0) * 100)}%</span></div>
            <div className="row"><span className="tag">campaign</span><span>campaign leads checked by scout gate</span><span className="score">{scoutCampaignQuality.latest_checked_count ?? 0}</span></div>
            <div className="row"><span className="tag">passed</span><span>campaign scout-quality passes</span><span className="score">{scoutCampaignQuality.latest_passed_count ?? 0}</span></div>
            <div className="row"><span className="tag">failed</span><span>campaign scout-quality failures</span><span className="score">{scoutCampaignQuality.latest_failed_count ?? 0}</span></div>
            <div className="row"><span className="tag">history</span><span>persisted scout quality snapshots</span><span className="score">{scoutQualityHistory.count ?? 0}</span></div>
            <div className="row"><span className="tag">latest</span><span>latest quality history status</span><span className="score">{latestScoutQualityHistory.status ?? "missing"}</span></div>
            <div className="row"><span className="tag">blockers</span><span>latest quality history blockers</span><span className="score">{latestScoutQualityHistory.blocker_count ?? 0}</span></div>
            <div className="row"><span className="tag">failed</span><span>latest quality history failed count</span><span className="score">{latestScoutQualityCampaign.latest_failed_count ?? 0}</span></div>
            <div className="row"><span className="tag">send</span><span>scout quality SMTP capability</span><span className="score">{scoutQualitySummary.send_mail ? "armed" : "no-send"}</span></div>
            <div className="row"><span className="tag">live</span><span>scout quality live outreach gate</span><span className="score">{scoutQualitySummary.live_outreach_allowed ? "armed" : "blocked"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in scout quality summary</span><span className="score">{scoutQualitySummary.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">secret</span><span>secrets in scout quality summary</span><span className="score">{scoutQualitySummary.secrets_included ? "blocked" : "omitted"}</span></div>
          </div>
          <div className="panel">
            <h2>Source Readiness Control</h2>
            <div className="row"><span className="tag">source</span><span>latest source readiness summary</span><span className="score">{scoutSourceReadiness.status ?? "missing"}</span></div>
            <div className="row"><span className="tag">checks</span><span>persisted source readiness checks</span><span className="score">{metrics.scout_source_readiness_checks ?? 0}</span></div>
            <div className="row"><span className="tag">sources</span><span>sources checked by latest readiness state</span><span className="score">{scoutSourceReadiness.sources_checked ?? 0}</span></div>
            <div className="row"><span className="tag">ready</span><span>sources ready for gated scout runs</span><span className="score">{scoutSourceReadiness.sources_ready ?? 0}</span></div>
            <div className="row"><span className="tag">blocked</span><span>sources held for review</span><span className="score">{scoutSourceReadiness.sources_blocked ?? 0}</span></div>
            <div className="row"><span className="tag">latest</span><span>latest source readiness status</span><span className="score">{scoutSourceReadinessLatest.status ?? "missing"}</span></div>
            <div className="row"><span className="tag">score</span><span>latest source readiness score</span><span className="score">{scoutSourceReadinessLatest.score ?? 0}</span></div>
            <div className="row"><span className="tag">rows</span><span>latest parseable input rows</span><span className="score">{scoutSourceReadinessLatest.parseable_count ?? 0}/{scoutSourceReadinessLatest.row_count ?? 0}</span></div>
            <div className="row"><span className="tag">dupes</span><span>latest duplicate domains</span><span className="score">{scoutSourceReadinessLatest.duplicate_domain_count ?? 0}</span></div>
            <div className="row"><span className="tag">excluded</span><span>latest excluded niches</span><span className="score">{scoutSourceReadinessLatest.excluded_niche_count ?? 0}</span></div>
            <div className="row"><span className="tag">invalid</span><span>latest invalid emails</span><span className="score">{scoutSourceReadinessLatest.invalid_email_count ?? 0}</span></div>
            <div className="row"><span className="tag">guard</span><span>source readiness regression guard</span><span className="score">{scoutSourceReadinessGuard.decision ?? "missing"}</span></div>
            <div className="row"><span className="tag">guard</span><span>source readiness regression count</span><span className="score">{scoutSourceReadinessGuard.regression_count ?? 0}</span></div>
            <div className="row"><span className="tag">review</span><span>source readiness review task</span><span className="score">{scoutSourceReadinessGuard.review_task_created ? "created" : "none"}</span></div>
            <div className="row"><span className="tag">send</span><span>source readiness SMTP capability</span><span className="score">{scoutSourceReadiness.send_mail || scoutSourceReadinessGuard.send_mail ? "armed" : "no-send"}</span></div>
            <div className="row"><span className="tag">live</span><span>source readiness live outreach gate</span><span className="score">{scoutSourceReadiness.live_outreach_allowed || scoutSourceReadinessGuard.live_outreach_allowed ? "armed" : "blocked"}</span></div>
            <div className="row"><span className="tag">privacy</span><span>raw recipients in source readiness payload</span><span className="score">{scoutSourceReadiness.raw_recipient_addresses_included || scoutSourceReadinessGuard.raw_recipient_addresses_included ? "blocked" : "omitted"}</span></div>
            <div className="row"><span className="tag">secret</span><span>secrets in source readiness payload</span><span className="score">{scoutSourceReadiness.secrets_included || scoutSourceReadinessGuard.secrets_included ? "blocked" : "omitted"}</span></div>
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
            <div className="segment-grid">
              <div className="segment-card">
                <span className="tag">cycle</span>
                <strong>{latestSelfCycle.status ?? "missing"}</strong>
                <span>latest closed-loop decision</span>
              </div>
              <div className="segment-card">
                <span className="tag">findings</span>
                <strong>{latestSelfCycle.findings_count ?? 0}</strong>
                <span>tracked quality and safety findings</span>
              </div>
              <div className="segment-card">
                <span className="tag">fixes</span>
                <strong>{latestSelfCycle.fix_tasks_created ?? 0}</strong>
                <span>new deduped self-fix tasks</span>
              </div>
              <div className="segment-card">
                <span className="tag">send</span>
                <strong>{latestSelfCycleResult.send_mail ? "armed" : "off"}</strong>
                <span>closed-loop mail capability</span>
              </div>
            </div>
            {selfOps.map(([label, value]) => (
              <div className="row" key={String(label)}><span className="tag">self</span><span>{String(label)}</span><span className="score">{String(value)}</span></div>
            ))}
            {selfCycles.length ? selfCycles.slice(0, 3).map((cycle: any) => (
              <div className="row" key={cycle.id}>
                <span className="tag">{cycle.status ?? "cycle"}</span>
                <span>{cycle.scope ?? "closed loop"}</span>
                <span className="score">{cycle.findings_count ?? 0}</span>
              </div>
            )) : <div className="row"><span className="tag">idle</span><span>no closed-loop cycles recorded yet</span><span className="score">0</span></div>}
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
