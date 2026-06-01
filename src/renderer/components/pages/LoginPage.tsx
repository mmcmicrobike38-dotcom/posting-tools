import { useState } from "react";
import { SimsoftDashboardModel } from "../../hooks/useSimsoftDashboard";
import simsoftLogo from "../../assets/simsoft-logo.png";

interface LoginPageProps {
  dashboard: SimsoftDashboardModel;
}

export function LoginPage({ dashboard }: LoginPageProps) {
  const { state, actions } = dashboard;
  const [showAccessRequest, setShowAccessRequest] = useState(false);
  const [requestName, setRequestName] = useState("");
  const [requestEmail, setRequestEmail] = useState("");
  const [showRequestSentPopup, setShowRequestSentPopup] = useState(false);
  const loginMessage = /login|sign|operator|google/i.test(state.message) ? state.message : "";
  const adminRecipients = state.status?.adminEmails ?? [];
  const configBlocking = Boolean(state.status && !state.status.configReady);
  const credentialItems = state.status?.credentialStatus ?? [];

  async function sendAccessRequest() {
    await actions.requestAccess({ email: requestEmail, name: requestName });
    setRequestName("");
    setRequestEmail("");
    setShowAccessRequest(false);
    setShowRequestSentPopup(true);
  }

  return (
    <main className="login-screen">
      <section className="login-card" aria-labelledby="login-title">
        <img className="login-logo" src={simsoftLogo} alt="" aria-hidden="true" />
        <div className="login-copy">
          <h1 id="login-title">{configBlocking ? "Setup Required" : showAccessRequest ? "Request Access" : "Posting Tools"}</h1>
          <p>
            {configBlocking
              ? "Add the required Google credential file before using Posting Tools."
              : showAccessRequest
                ? "Enter your Google email so an admin can approve your account."
                : "Sign in with your Google account to continue."}
          </p>
        </div>

        {configBlocking ? (
          <section className="access-request-form" aria-label="First-run credential setup">
            <div className="login-error" role="status">
              Required configuration is missing or invalid.
            </div>
            <dl className="modal-facts">
              <div className="modal-fact-row">
                <dt>Config folder</dt>
                <dd>{state.status?.configDir}</dd>
              </div>
              {credentialItems.filter((item) => item.required || !item.ok).map((item) => (
                <div className="modal-fact-row" key={item.fileName}>
                  <dt>{item.fileName}</dt>
                  <dd>{item.ok ? "Ready" : item.message}</dd>
                </div>
              ))}
            </dl>
            <button className="login-button" type="button" onClick={() => actions.openSupportFolder("config")} disabled={state.busy}>
              Open Config Folder
            </button>
            <button className="request-access-link" type="button" onClick={actions.runHealthCheck} disabled={state.busy}>
              Run Health Check
            </button>
            {state.message ? <small>{state.message}</small> : null}
            {state.healthCheck?.items.length ? (
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
            ) : null}
          </section>
        ) : showAccessRequest ? (
          <form
            className="access-request-form"
            onSubmit={(event) => {
              event.preventDefault();
              void sendAccessRequest();
            }}
          >
            <input
              value={requestName}
              onChange={(event) => setRequestName(event.target.value)}
              placeholder="Full name"
              aria-label="Full name"
              disabled={state.busy}
              required
            />
            <input
              type="email"
              value={requestEmail}
              onChange={(event) => setRequestEmail(event.target.value)}
              placeholder="Google email"
              aria-label="Google email"
              disabled={state.busy}
              required
            />
            <button type="submit" disabled={state.busy || !requestEmail.trim()}>
              {state.busy ? "Sending..." : "Send Request"}
            </button>
            <button className="access-back-button" type="button" onClick={() => setShowAccessRequest(false)} disabled={state.busy}>
              Back to login
            </button>
            <small>{adminRecipients.length ? `Request goes to ${adminRecipients.join(", ")}` : "Admin email must be configured first."}</small>
          </form>
        ) : (
          <>
            <button className="login-button" type="button" onClick={actions.loginGoogleOperator} disabled={state.busy}>
              {state.busy ? "Opening Google..." : "Continue with Google"}
            </button>

            <button className="request-access-link" type="button" onClick={() => setShowAccessRequest(true)} disabled={state.busy}>
              Request Access
            </button>
          </>
        )}

        {state.busy ? (
          <div className="login-waiting" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <div>
              <strong>Complete Google sign-in</strong>
              <p>Use the browser window that opened. Posting Tools will continue automatically after login.</p>
            </div>
          </div>
        ) : null}

        {state.operatorIdentity?.error || loginMessage ? (
          <div className="login-error" role="status">
            {state.operatorIdentity?.error || loginMessage}
          </div>
        ) : null}
      </section>

      {showRequestSentPopup ? (
        <div className="request-sent-overlay" role="presentation">
          <section className="request-sent-dialog" role="dialog" aria-modal="true" aria-labelledby="request-sent-title">
            <div className="request-sent-mark" aria-hidden="true">OK</div>
            <h2 id="request-sent-title">Request Sent</h2>
            <p>Your request has been sent to the admin. Please wait for their update.</p>
            <button className="login-button" type="button" onClick={() => setShowRequestSentPopup(false)}>
              Back to Login
            </button>
          </section>
        </div>
      ) : null}
    </main>
  );
}
