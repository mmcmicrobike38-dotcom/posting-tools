import { useEffect, useState } from "react";
import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import { ModalShell } from "../modals/ModalShell";

interface AdvancedSettingsPageProps {
  dashboard: SimsoftDashboardModel;
}

export function AdvancedSettingsPage({ dashboard }: AdvancedSettingsPageProps) {
  const { state, derived, actions } = dashboard;
  const checkedAt = state.healthCheck?.checkedAt ? new Date(state.healthCheck.checkedAt).toLocaleString() : "Not checked yet";
  const googleItems = derived.setupChecklist.filter((item) => ["Google login", "Drive folder"].includes(item.label));
  const currentEmail = state.operatorIdentity?.email.trim().toLowerCase() ?? "";
  const [assignmentEmail, setAssignmentEmail] = useState("");
  const [assignmentRole, setAssignmentRole] = useState<"admin" | "member">("member");
  const [assignmentBranches, setAssignmentBranches] = useState("");
  const [activeSection, setActiveSection] = useState<"google" | "access" | "other" | "health">("google");
  const [settingsSearch, setSettingsSearch] = useState("");
  const [pendingAccessSave, setPendingAccessSave] = useState(false);
  const [editingAccess, setEditingAccess] = useState(false);
  const [removeAccessEmail, setRemoveAccessEmail] = useState("");
  const [discardSettingsConfirm, setDiscardSettingsConfirm] = useState(false);
  const accessList = [
    ...(state.status?.adminEmails ?? []).map((email) => ({ email, role: "Admin", branches: ["*"] })),
    ...(state.status?.memberEmails ?? [])
      .filter((email) => !(state.status?.adminEmails ?? []).includes(email))
      .map((email) => ({ email, role: "Member", branches: state.status?.userBranches[email] ?? [] }))
  ];
  const knownOperators = state.status?.knownOperators ?? [];
  const assignedEmails = new Set(accessList.map((item) => item.email));
  const unassignedKnownOperators = knownOperators.filter((operator) => !assignedEmails.has(operator.email));
  const accessRequests = (state.status?.accessRequests ?? []).filter((request) => !assignedEmails.has(request.email));
  const knownUserOptions = [...new Set([...accessList.map((item) => item.email), ...knownOperators.map((operator) => operator.email), ...accessRequests.map((request) => request.email), currentEmail].filter(Boolean))].sort();
  const hasUnsavedAccessDraft = Boolean(assignmentEmail.trim() || assignmentBranches.trim() || assignmentRole !== "member");
  const settingsSections = [
    { id: "google" as const, label: "Google Settings", keywords: "google login drive folder sheet access credentials" },
    { id: "access" as const, label: "Access List", keywords: "users team members roles branches remove edit save access" },
    { id: "other" as const, label: "Other Settings", keywords: "version cache logs duplicate history summary tools clear cache" },
    { id: "health" as const, label: "Health Check", keywords: "health check google drive cache logs credentials files" }
  ];
  const normalizedSettingsSearch = settingsSearch.trim().toLowerCase();
  const visibleSettingsSections = settingsSections.filter(
    (section) => !normalizedSettingsSearch || `${section.label} ${section.keywords}`.toLowerCase().includes(normalizedSettingsSearch)
  );

  function resetAccessDraft() {
    setAssignmentEmail("");
    setAssignmentBranches("");
    setAssignmentRole("member");
    setEditingAccess(false);
    setPendingAccessSave(false);
  }

  function closeSettings() {
    if (hasUnsavedAccessDraft) {
      setDiscardSettingsConfirm(true);
      return;
    }
    actions.setShowAdvancedSettings(false);
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") closeSettings();
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [actions, hasUnsavedAccessDraft]);

  function emailDisplayName(email: string): string {
    const local = email.split("@", 1)[0] || email;
    const readable = local
      .replace(/[._-]+/g, " ")
      .replace(/([a-zA-Z])(\d)/g, "$1 $2")
      .replace(/(\d)([a-zA-Z])/g, "$1 $2")
      .replace(/\bmmc\b/gi, "MMC")
      .replace(/\b\w/g, (letter) => letter.toUpperCase())
      .trim();
    return readable || email;
  }

  function googleDisplayName(email: string): string {
    if (email === currentEmail && state.operatorIdentity?.name) return state.operatorIdentity.name;
    const knownOperator = knownOperators.find((operator) => operator.email === email);
    return knownOperator?.name || emailDisplayName(email);
  }

  function branchPills(email: string, branches: string[]) {
    return branches.map((branch) => (
      <span className="branch-summary-pill" key={`${email}-${branch}`}>
        {branch}
      </span>
    ));
  }

  const loadedBranchCount = Object.keys(state.scanResult?.branchIndex ?? {}).length;
  const availableBranches = Object.values(state.scanResult?.branchIndex ?? {}).sort((first, second) =>
    first.branch_id.localeCompare(second.branch_id)
  );
  const selectedBranches = assignmentBranches
    .split(",")
    .map((branch) => branch.trim().toUpperCase())
    .filter(Boolean);
  const selectedBranchSet = new Set(selectedBranches);
  const unassignedBranches = availableBranches.filter((branch) => !selectedBranchSet.has(branch.branch_id.toUpperCase()));

  function setSelectedBranches(branches: string[]) {
    setAssignmentBranches([...new Set(branches.map((branch) => branch.trim().toUpperCase()).filter(Boolean))].join(", "));
  }

  function addBranch(branchId: string) {
    setSelectedBranches([...selectedBranches, branchId]);
  }

  function removeBranch(branchId: string) {
    setSelectedBranches(selectedBranches.filter((branch) => branch !== branchId));
  }

  function handleBranchDrop(branchId: string) {
    if (assignmentRole === "admin") return;
    addBranch(branchId);
  }

  async function saveAssignment() {
    const email = assignmentEmail.trim().toLowerCase();
    if (!email) return;
    const branches = assignmentBranches
      .split(",")
      .map((branch) => branch.trim().toUpperCase())
      .filter(Boolean);
    const adminEmails = new Set(state.status?.adminEmails ?? []);
    const memberEmails = new Set(state.status?.memberEmails ?? []);
    const userBranches = { ...(state.status?.userBranches ?? {}) };
    if (state.isAdmin && currentEmail && email !== currentEmail) {
      adminEmails.add(currentEmail);
      memberEmails.delete(currentEmail);
      userBranches[currentEmail] = ["*"];
    }
    if (assignmentRole === "admin") {
      adminEmails.add(email);
      memberEmails.delete(email);
      userBranches[email] = ["*"];
    } else {
      memberEmails.add(email);
      adminEmails.delete(email);
      userBranches[email] = branches;
    }
    const saved = await actions.saveAccessConfig({
      adminEmails: [...adminEmails],
      memberEmails: [...memberEmails],
      userBranches
    });
    if (!saved) return;
    resetAccessDraft();
  }

  function editAssignment(email: string, role: string, branches: string[]) {
    setAssignmentEmail(email);
    setAssignmentRole(role === "Admin" ? "admin" : "member");
    setAssignmentBranches(branches.includes("*") ? "" : branches.join(", "));
    setEditingAccess(true);
  }

  function selectKnownUser(email: string) {
    setAssignmentEmail(email);
    const assigned = accessList.find((item) => item.email === email);
    setAssignmentRole(assigned?.role === "Admin" ? "admin" : "member");
    setAssignmentBranches(assigned?.branches.includes("*") ? "" : assigned?.branches.join(", ") ?? "");
  }

  async function removeAssignment(email: string) {
    const adminEmails = (state.status?.adminEmails ?? []).filter((item) => item !== email);
    const memberEmails = (state.status?.memberEmails ?? []).filter((item) => item !== email);
    const userBranches = { ...(state.status?.userBranches ?? {}) };
    delete userBranches[email];
    const saved = await actions.saveAccessConfig({ adminEmails, memberEmails, userBranches });
    if (saved) setRemoveAccessEmail("");
  }

  function prepareKnownOperator(email: string) {
    setAssignmentEmail(email);
    setAssignmentRole("member");
    setAssignmentBranches("");
  }

  function prepareAccessRequest(email: string) {
    setAssignmentEmail(email);
    setAssignmentRole("member");
    setAssignmentBranches("");
    setActiveSection("access");
  }

  async function copyText(value: string) {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const input = document.createElement("textarea");
      input.value = value;
      input.setAttribute("readonly", "true");
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      document.body.removeChild(input);
    }
  }

  async function acceptAccessRequest(email: string) {
    prepareAccessRequest(email);
    await copyText(email);
    await actions.openGoogleTestUsersPage();
  }

  async function declineAccessRequest(email: string) {
    const saved = await actions.saveAccessConfig({
      adminEmails: state.status?.adminEmails ?? [],
      memberEmails: state.status?.memberEmails ?? [],
      userBranches: state.status?.userBranches ?? {},
      accessRequests: (state.status?.accessRequests ?? []).filter((request) => request.email !== email),
      successMessage: "Access request declined.",
      successToast: "Request declined"
    });
    if (saved && assignmentEmail === email) resetAccessDraft();
  }

  function updateSettingsSearch(value: string) {
    const normalized = value.trim().toLowerCase();
    setSettingsSearch(value);
    if (!normalized) return;
    const firstMatch = settingsSections.find((section) => `${section.label} ${section.keywords}`.toLowerCase().includes(normalized));
    if (firstMatch) setActiveSection(firstMatch.id);
  }

  return (
    <div className="advanced-page-backdrop" role="presentation">
      <section className="advanced-page settings-browser" role="dialog" aria-modal="true" aria-labelledby="advanced-page-title">
        <header className="advanced-page-header settings-browser-header">
          <h2 id="advanced-page-title">Settings</h2>
          <input
            className="settings-search"
            value={settingsSearch}
            onChange={(event) => updateSettingsSearch(event.target.value)}
            placeholder="Search settings, users, branches, tools..."
            aria-label="Search settings"
          />
          {state.isAdmin ? (
            <button className={accessRequests.length ? "notification-button active" : "notification-button"} onClick={() => setActiveSection("access")} title="Access requests">
              <span aria-hidden="true">!</span>
              Requests
              <strong>{accessRequests.length}</strong>
            </button>
          ) : null}
          <button className="icon-button" onClick={closeSettings} aria-label="Close advanced settings (Esc)" title="Esc">X</button>
        </header>

        <div className="settings-browser-body">
          <nav className="settings-nav" aria-label="Advanced settings sections">
            {visibleSettingsSections.length ? (
              visibleSettingsSections.map((section) => (
                <button className={activeSection === section.id ? "active" : ""} onClick={() => setActiveSection(section.id)} key={section.id}>
                  {section.label}
                </button>
              ))
            ) : (
              <p className="cache-note">No settings match that search.</p>
            )}
          </nav>

          <main className="settings-content">
            <div className="settings-content-header">
              <h3>
                {activeSection === "google" ? "Google Settings" : null}
                {activeSection === "access" ? "Access List" : null}
                {activeSection === "other" ? "Other Settings" : null}
                {activeSection === "health" ? "Health Check" : null}
              </h3>
              <span>{state.message || "Ready"}</span>
            </div>

            {activeSection === "google" ? (
              <>
                <section className="settings-card">
                  {googleItems.map((item) => (
                    <div className="settings-item" key={item.label}>
                      <div>
                        <strong>{item.label}</strong>
                        <p>{item.done ? "Ready" : "Needed"}</p>
                      </div>
                      <span className={item.done ? "role-pill ready" : "role-pill"}>{item.done ? "Ready" : "Needed"}</span>
                    </div>
                  ))}
                </section>
                <section className="settings-card">
                  <dl className="settings-facts">
                    <dt>Operator</dt>
                    <dd>{state.operatorIdentity?.email || "Not signed in"}</dd>
                    <dt>Role</dt>
                    <dd>{state.userRole === "admin" ? "Admin" : "Member"}</dd>
                    <dt>Folder</dt>
                    <dd>{state.savedFolderUrl || state.folderUrl || "Not saved"}</dd>
                    <dt>Sheet Access</dt>
                    <dd className="copyable-setting">
                      <span>{state.scanResult?.serviceAccountEmail || "Scan folder first"}</span>
                      <button
                        className="copy-icon-button"
                        onClick={actions.copyServiceAccountEmail}
                        disabled={state.busy || !state.scanResult?.serviceAccountEmail}
                        aria-label="Copy sheet access email"
                      >
                        <span aria-hidden="true" />
                      </button>
                    </dd>
                  </dl>
                </section>
                {state.isAdmin ? (
                  <details className="settings-card technical-details">
                    <summary>Technical Details</summary>
                    <dl className="settings-facts">
                      <dt>Google Mode</dt>
                      <dd>{state.effectiveGoogleAuthMode ?? state.status?.authMode ?? "service_account"}</dd>
                      <dt>Token Folder</dt>
                      <dd>{state.status?.oauthTokenDir ?? ""}</dd>
                      <dt>Client File</dt>
                      <dd>{state.status?.oauthClientJsonPath ?? ""}</dd>
                      <dt>Credential File</dt>
                      <dd>{state.status?.serviceAccountJsonPath ?? ""}</dd>
                    </dl>
                  </details>
                ) : null}
                {state.isAdmin ? (
                  <section className="settings-card">
                    <button onClick={() => actions.setActiveModal("googleTestUsersConfirm")} disabled={state.busy}>
                      Open Google Test Users Page
                    </button>
                  </section>
                ) : null}
              </>
            ) : null}

            {activeSection === "access" ? (
              <>
              {state.isAdmin ? (
                <section className={accessRequests.length ? "settings-card access-requests-card has-requests" : "settings-card access-requests-card"}>
                  <div className="side-card-header">
                    <h3>Access Requests</h3>
                    <span>{accessRequests.length ? `${accessRequests.length} pending` : "No pending requests"}</span>
                  </div>
                  {accessRequests.length ? (
                    <div className="assignment-table access-requests-table">
                      <div className="assignment-table-head">
                        <span>Name</span>
                        <span>Status</span>
                        <span>Requested</span>
                        <span>Action</span>
                      </div>
                      {accessRequests.map((request) => (
                        <div className="assignment-table-row" key={request.email}>
                          <div className="assignment-user-cell">
                            <span className="member-avatar">{(request.name || emailDisplayName(request.email)).slice(0, 1).toUpperCase()}</span>
                            <div>
                              <strong>{request.name || emailDisplayName(request.email)}</strong>
                              <p>{request.email}</p>
                            </div>
                          </div>
                          <span className="role-pill">Pending</span>
                          <span className="assignment-branches-cell">
                            {request.lastRequestedAt ? new Date(request.lastRequestedAt).toLocaleString() : "Recently"}
                          </span>
                          <div className="member-actions request-actions">
                            <button onClick={() => void acceptAccessRequest(request.email)} disabled={state.busy}>Accept</button>
                            <button className="danger-outline" onClick={() => void declineAccessRequest(request.email)} disabled={state.busy}>Decline</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="cache-note">New account requests will appear here after users click Request Access on the login screen.</p>
                  )}
                </section>
              ) : null}
              <section className="settings-card member-list">
                <div className="side-card-header">
                  <h3>Access List</h3>
                  <span>{accessList.length ? `${accessList.length} user(s)` : "Not configured"}</span>
                </div>
            {state.isAdmin ? (
              <div className="assignment-editor">
                <div className="assignment-row">
                  <div className="email-entry-field">
                    {knownUserOptions.length ? (
                      <select value={assignmentEmail} onChange={(event) => selectKnownUser(event.target.value)}>
                        <option value="">Select team member</option>
                        {knownUserOptions.map((email) => (
                          <option key={email} value={email}>
                            {googleDisplayName(email)} - {email}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        value={assignmentEmail}
                        onChange={(event) => setAssignmentEmail(event.target.value)}
                        placeholder="Type or paste member email"
                      />
                    )}
                  </div>
                  <select value={assignmentRole} onChange={(event) => setAssignmentRole(event.target.value as "admin" | "member")}>
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
                <div className="assignment-row assignment-row-branches">
                  <input
                    value={assignmentBranches}
                    onChange={(event) => setAssignmentBranches(event.target.value)}
                    placeholder={assignmentRole === "admin" ? "All branches" : "MMC038, MMC075"}
                    disabled={assignmentRole === "admin"}
                  />
                  <button className="success-action" onClick={() => setPendingAccessSave(true)} disabled={!assignmentEmail.trim()}>
                    Save
                  </button>
                </div>
                {assignmentRole === "member" ? (
                  <div className="branch-assignment-picker">
                    <div>
                      <strong>All Branches</strong>
                      <div className="branch-chip-list">
                        {unassignedBranches.map((branch) => (
                          <button
                            key={branch.branch_id}
                            className="branch-chip"
                            draggable
                            onDragStart={(event) => event.dataTransfer.setData("text/plain", branch.branch_id)}
                            onClick={() => addBranch(branch.branch_id)}
                            title={branch.branch_name || branch.file_name}
                          >
                            {branch.branch_id}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div
                      className="assigned-branch-dropzone"
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        handleBranchDrop(event.dataTransfer.getData("text/plain"));
                      }}
                    >
                      <strong>Assigned</strong>
                      <div className="branch-chip-list">
                        {selectedBranches.length ? (
                          selectedBranches.map((branchId) => (
                            <button key={branchId} className="branch-chip assigned" onClick={() => removeBranch(branchId)}>
                              {branchId}
                            </button>
                          ))
                        ) : (
                          <p className="cache-note">Drag branches here or click a branch.</p>
                        )}
                      </div>
                    </div>
                  </div>
                ) : null}
                <p className="cache-note">{loadedBranchCount ? `${loadedBranchCount} branch sheets loaded.` : "Scan folder to load branch IDs."}</p>
              </div>
            ) : null}
              </section>
            {accessList.length ? (
              <section className="settings-card assignment-list-card">
                <div className="side-card-header">
                  <h3>Assigned Users</h3>
                  <span>{accessList.length} user(s)</span>
                </div>
              <div className="assignment-table">
                <div className="assignment-table-head">
                  <span>Name</span>
                  <span>Role</span>
                  <span>Assigned Branch</span>
                  {state.isAdmin ? <span>Action</span> : null}
                </div>
                {accessList.map((item) => (
                  <div className="assignment-table-row" key={`${item.role}-${item.email}`}>
                    <div className="assignment-user-cell">
                      <span className="member-avatar">{googleDisplayName(item.email).slice(0, 1).toUpperCase()}</span>
                      <div>
                        <strong>{googleDisplayName(item.email)}</strong>
                        <p>{item.email}{item.email === currentEmail ? " - Current user" : ""}</p>
                      </div>
                    </div>
                    <span className={item.role === "Admin" ? "role-pill admin" : "role-pill"}>{item.role}</span>
                    <span className="assignment-branches-cell">
                      {item.role === "Admin" ? (
                        <span className="branch-summary-pill">All branches</span>
                      ) : item.branches.length ? (
                        branchPills(item.email, item.branches)
                      ) : (
                        <span className="branch-summary-pill muted">None</span>
                      )}
                    </span>
                    {state.isAdmin ? (
                      <div className="member-actions">
                        <button onClick={() => editAssignment(item.email, item.role, item.branches)}>Edit</button>
                        <button className="danger-outline" onClick={() => setRemoveAccessEmail(item.email)}>Remove</button>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
              </section>
            ) : (
              <p className="cache-note">Add emails in SIMSOFT_ADMIN_EMAILS or SIMSOFT_MEMBER_EMAILS to show them here.</p>
            )}
            {unassignedKnownOperators.length ? (
              <section className="settings-card assignment-list-card">
                <div className="side-card-header">
                  <h3>Recent Google Users</h3>
                  <span>{unassignedKnownOperators.length} unassigned</span>
                </div>
                <div className="assignment-table">
                  <div className="assignment-table-head">
                    <span>Name</span>
                    <span>Role</span>
                    <span>Last Seen</span>
                    {state.isAdmin ? <span>Action</span> : null}
                  </div>
                  {unassignedKnownOperators.map((operator) => (
                    <div className="assignment-table-row" key={operator.email}>
                      <div className="assignment-user-cell">
                        <span className="member-avatar">{emailDisplayName(operator.email).slice(0, 1).toUpperCase()}</span>
                        <div>
                          <strong>{operator.name || emailDisplayName(operator.email)}</strong>
                          <p>{operator.email}</p>
                        </div>
                      </div>
                      <span className="role-pill">Unassigned</span>
                      <span className="assignment-branches-cell">
                        {operator.lastSeenAt ? new Date(operator.lastSeenAt).toLocaleString() : "Recently"}
                      </span>
                      {state.isAdmin ? (
                        <div className="member-actions">
                          <button onClick={() => prepareKnownOperator(operator.email)}>Assign</button>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
              </>
            ) : null}

            {activeSection === "other" ? (
              <>
                <section className="settings-card">
                  <dl className="settings-facts">
                    <dt>Version</dt>
                    <dd>{state.status?.appVersion ?? "Unknown"}</dd>
                  <dt>Data Cache</dt>
                  <dd>{state.status?.cachePath ? "Ready" : "Not found"}</dd>
                  <dt>Logs</dt>
                  <dd>{state.status?.logDir ? "Ready" : "Not found"}</dd>
                  <dt>Access List</dt>
                  <dd>{state.status?.accessControlPath ? "Ready" : "Not found"}</dd>
                </dl>
                <details className="technical-details">
                  <summary>Technical Details</summary>
                  <dl className="settings-facts">
                    <dt>Cache Folder</dt>
                    <dd>{state.status?.cachePath ?? ""}</dd>
                    <dt>Logs Folder</dt>
                    <dd>{state.status?.logDir ?? ""}</dd>
                    <dt>Access File</dt>
                    <dd>{state.status?.accessControlPath ?? ""}</dd>
                  </dl>
                </details>
              </section>
              <section className="settings-card settings-actions">
                <button onClick={actions.runHealthCheck} disabled={state.busy}>{state.busy ? "Checking..." : "Run Health Check"}</button>
                {state.isAdmin ? (
                  <>
                      <button onClick={() => actions.setActiveModal("settingsSummary")}>Open Settings Summary</button>
                      <button className="warning-action" onClick={() => actions.setActiveModal("resetDuplicates")}>Duplicate History</button>
                      <button className="warning-action" onClick={() => actions.setActiveModal("clearCacheConfirm")} disabled={state.busy}>Clear Cache</button>
                    </>
                  ) : (
                    <p className="cache-note">Member access hides maintenance actions.</p>
                  )}
                </section>
              </>
            ) : null}

            {activeSection === "health" ? (
              <section className="settings-card">
                <div className="side-card-header">
                  <h3>Health Check</h3>
                  <span>{state.healthCheck?.ok ? "Passed" : state.healthCheck ? "Needs attention" : checkedAt}</span>
                </div>
                {state.healthCheck ? (
                  <div className="health-list">
                    {state.healthCheck.items.map((item) => (
                      <div className={item.ok ? "health-row ok" : "health-row"} key={item.label}>
                        <i aria-hidden="true" />
                        <div>
                          <strong>{item.label}</strong>
                          <p>{item.detail}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="cache-note">Run a health check to verify local files and folders.</p>
                )}
              </section>
            ) : null}

          </main>
        </div>
        {pendingAccessSave ? (
          <ModalShell
            title="Save User Access?"
            titleId="save-access-title"
            closeLabel="Close save access confirmation"
            className="compact-modal"
            onClose={() => setPendingAccessSave(false)}
            footer={
              <>
                <button onClick={() => setPendingAccessSave(false)} disabled={state.busy}>Cancel</button>
                <button className="primary" data-default-action="true" onClick={() => void saveAssignment()} disabled={state.busy || !assignmentEmail.trim()}>
                  {state.busy ? "Saving..." : "Save User Access"}
                </button>
              </>
            }
          >
            <p>This will update the selected team member's role and assigned branches.</p>
            <dl className="modal-facts">
              <dt>User</dt>
              <dd>{assignmentEmail || "No user selected"}</dd>
              <dt>Role</dt>
              <dd>{assignmentRole === "admin" ? "Admin" : "Member"}</dd>
              <dt>Branches</dt>
              <dd>{assignmentRole === "admin" ? "All branches" : assignmentBranches || "None selected"}</dd>
            </dl>
          </ModalShell>
        ) : null}
        {editingAccess ? (
          <ModalShell
            title="Edit User"
            titleId="edit-access-title"
            closeLabel="Close edit user form"
            onClose={resetAccessDraft}
            footer={
              <>
                <button onClick={resetAccessDraft} disabled={state.busy}>Cancel</button>
                <button className="primary" data-default-action="true" onClick={() => void saveAssignment()} disabled={state.busy || !assignmentEmail.trim()}>
                  {state.busy ? "Saving..." : "Save Changes"}
                </button>
              </>
            }
          >
            <label>
              Name
              <input value={emailDisplayName(assignmentEmail)} readOnly />
            </label>
            <label>
              Email
              <input value={assignmentEmail} readOnly />
            </label>
            <label>
              Role
              <select value={assignmentRole} onChange={(event) => setAssignmentRole(event.target.value as "admin" | "member")}>
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <label>
              Assigned branches
              <input
                value={assignmentBranches}
                onChange={(event) => setAssignmentBranches(event.target.value)}
                placeholder={assignmentRole === "admin" ? "All branches" : "MMC038, MMC075"}
                disabled={assignmentRole === "admin"}
              />
            </label>
          </ModalShell>
        ) : null}
        {removeAccessEmail ? (
          <ModalShell
            title="Remove User Access?"
            titleId="remove-access-title"
            closeLabel="Close remove user confirmation"
            className="compact-modal destructive-modal"
            onClose={() => setRemoveAccessEmail("")}
            footer={
              <>
                <button onClick={() => setRemoveAccessEmail("")} disabled={state.busy}>Cancel</button>
                <button className="danger" onClick={() => void removeAssignment(removeAccessEmail)} disabled={state.busy}>
                  {state.busy ? "Removing..." : "Remove User"}
                </button>
              </>
            }
          >
            <p>This user will no longer be able to access assigned branches in SIMSOFT.</p>
            <dl className="modal-facts">
              <dt>User</dt>
              <dd>{emailDisplayName(removeAccessEmail)}</dd>
              <dt>Email</dt>
              <dd>{removeAccessEmail}</dd>
            </dl>
          </ModalShell>
        ) : null}
        {discardSettingsConfirm ? (
          <ModalShell
            title="Discard unsaved changes?"
            titleId="discard-settings-title"
            closeLabel="Close discard confirmation"
            className="compact-modal warning-modal"
            onClose={() => setDiscardSettingsConfirm(false)}
            footer={
              <>
                <button onClick={() => setDiscardSettingsConfirm(false)}>Cancel</button>
                <button
                  className="danger"
                  onClick={() => {
                    resetAccessDraft();
                    setDiscardSettingsConfirm(false);
                    actions.setShowAdvancedSettings(false);
                  }}
                >
                  Discard
                </button>
              </>
            }
          >
            <p>You have an unfinished access list change. Closing now will discard that draft.</p>
          </ModalShell>
        ) : null}
        {state.toastMessage ? <div className="toast-popup" role="status">{state.toastMessage}</div> : null}
      </section>
    </div>
  );
}
