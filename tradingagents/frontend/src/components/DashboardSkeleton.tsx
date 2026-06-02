/**
 * Skeleton placeholders shown on first paint while the REST/WebSocket
 * connection settles. Mirrors the real Dashboard layout (metrics row +
 * watchlist + 2-col body) so the transition to data feels seamless.
 */
export function DashboardSkeleton() {
  return (
    <div>
      <div className="container" style={{ marginBottom: 24 }}>
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card">
            <div className="skeleton skeleton-line sm" />
            <div className="skeleton skeleton-line lg" style={{ marginTop: 14 }} />
            <div className="skeleton skeleton-line sm" style={{ marginTop: 8, width: '55%' }} />
          </div>
        ))}
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="skeleton skeleton-line sm" />
        <div style={{ display: 'grid', gap: 10, marginTop: 16 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '120px 1fr 1fr 80px 60px', gap: 14 }}>
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-line" />
              <div className="skeleton skeleton-line" />
            </div>
          ))}
        </div>
      </div>

      <div className="container">
        <div className="card grid-2col">
          <div className="skeleton skeleton-line sm" />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, marginTop: 16 }}>
            {[0, 1, 2, 3].map((i) => (
              <div key={i}>
                <div className="skeleton skeleton-line sm" />
                <div className="skeleton skeleton-line lg" style={{ marginTop: 8 }} />
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="skeleton skeleton-line sm" />
          <div className="skeleton" style={{ marginTop: 14, height: 220, borderRadius: 'var(--radius-sm)' }} />
        </div>

        <div className="card">
          <div className="skeleton skeleton-line sm" />
          <div className="skeleton" style={{ marginTop: 14, height: 220, borderRadius: 'var(--radius-sm)' }} />
        </div>
      </div>
    </div>
  )
}
