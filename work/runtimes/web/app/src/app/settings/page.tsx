/* Placeholder. The shell, navigation and design system are real; this surface is
 * not built yet. It says so rather than rendering an empty frame that looks
 * finished, because a page that looks done and does nothing is worse than a page
 * that admits what it is. */
export default function Page() {
  return (
    <>
      <header className="page-head">
        <h1 className="page-title">Settings</h1>
        <p className="page-sub">Surfaces, tools and policy, read from the tracked configuration.</p>
      </header>
      <div className="panel">
        <div className="card-body stack">
          <span className="badge badge-warn">not built yet</span>
          <p className="muted" style={{ margin: 0 }}>
            The gateway behind this surface is serving. This view is the remaining work.
          </p>
        </div>
      </div>
    </>
  );
}
