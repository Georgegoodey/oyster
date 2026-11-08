import { useEffect, useMemo, useState } from 'react'
import './App.css'

const TIMES = [15, 30, 45, 60, 90]
const PAGE = 20

function VendorRow({ v }) {
  return (
    <div className="card">
      <h3>
        {v.name} <span className="tag">{v.kind}</span>
      </h3>
      <div className="body">
        <p className="muted">
          {v.minutes} min {v.minutes_source === 'driving' ? 'drive' : '(est.)'} · {v.km} km
          {v.address ? ` · ${v.address}` : ''}
        </p>
        {v.hours && <p className="muted">{v.hours}</p>}
        <div className="links">
          {v.website && (
            <a className="small" href={v.website} target="_blank" rel="noreferrer">
              Website ↗
            </a>
          )}
          {v.phone && <span className="small">{v.phone}</span>}
          <a
            className="small"
            href={`https://www.google.com/maps/search/?api=1&query=${v.lat},${v.lon}`}
            target="_blank"
            rel="noreferrer"
          >
            Map ↗
          </a>
        </div>
      </div>
    </div>
  )
}

function Products({ products }) {
  return products.map((p) => (
    <a className="product" key={p.url} href={p.url} target="_blank" rel="noreferrer">
      {p.image && <img src={p.image} alt="" />}
      <span>{p.name}</span>
      <b>{p.price}</b>
    </a>
  ))
}

// Detailed errors go to the console; the page only shows a friendly message.
function friendly(err, what) {
  console.error(`[${what}]`, err)
  if (!navigator.onLine || err instanceof TypeError) {
    return 'We could not reach the server. Please check your internet connection and try again.'
  }
  return what === 'search'
    ? 'Something went wrong with your search. Please try again.'
    : 'Something went wrong loading the vendor list. Please try again.'
}

export default function App() {
  const [query, setQuery] = useState('')
  const [minutes, setMinutes] = useState(60)
  const [data, setData] = useState(null)
  const [vendors, setVendors] = useState(null)
  const [vendorError, setVendorError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [kind, setKind] = useState('All')
  const [filter, setFilter] = useState('')
  const [shown, setShown] = useState(PAGE)

  // Vendor directory: reloads when the travel-time limit changes.
  useEffect(() => {
    let live = true
    setVendors(null)
    setVendorError(null)
    fetch(`/api/vendors?max_minutes=${minutes}`)
      .then((r) => (r.ok ? r.json() : r.json().then((j) => Promise.reject(new Error(j.detail || r.status)))))
      .then((v) => live && setVendors(v))
      .catch((e) => live && setVendorError(friendly(e, 'vendors')))
    return () => {
      live = false
    }
  }, [minutes])

  // Reads the NDJSON stream and updates the page as each source or vendor reports back.
  async function search(e) {
    e?.preventDefault()
    setLoading(true)
    setError(null)
    setData({ sources: [], hits: [], done: 0, total: 0, vendors: 0 })
    try {
      const r = await fetch(`/api/search?q=${encodeURIComponent(query)}&max_minutes=${minutes}`)
      if (!r.ok) throw new Error(`Server returned ${r.status}`)
      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const apply = (ev) => {
        if (ev.type === 'source' && !ev.result.ok) console.error(`[source: ${ev.result.source}]`, ev.result.error)
        setData((d) => {
          if (ev.type === 'start') return { ...d, total: ev.total, vendors: ev.vendors }
          if (ev.type === 'source') return { ...d, done: ev.done, sources: [...d.sources, ev.result] }
          if (ev.type === 'vendor') return { ...d, done: ev.done, hits: ev.hit ? [...d.hits, ev.hit] : d.hits }
          return d
        })
      }
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        lines.filter(Boolean).forEach((l) => apply(JSON.parse(l)))
      }
    } catch (err) {
      setError(friendly(err, 'search'))
    } finally {
      setLoading(false)
    }
  }

  const kinds = useMemo(() => ['All', ...new Set((vendors || []).map((v) => v.kind))], [vendors])
  const visible = useMemo(() => {
    const f = filter.trim().toLowerCase()
    return (vendors || []).filter(
      (v) =>
        (kind === 'All' || v.kind === kind) &&
        (!f || `${v.name} ${v.address}`.toLowerCase().includes(f)),
    )
  }, [vendors, kind, filter])

  return (
    <div className="page">
      <nav className="nav">
        <strong>Oyster</strong>
        <span>
          <a href="#results">Search</a>
          <a href="#vendors">Vendors</a>
        </span>
      </nav>

      <form onSubmit={search}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for food, e.g. eggs, sourdough, cheese"
          minLength={2}
          required
        />
        <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} aria-label="Maximum travel time">
          {TIMES.map((t) => (
            <option key={t} value={t}>
              {t} min
            </option>
          ))}
        </select>
        <button disabled={loading}>{loading ? 'Searching…' : 'Search'}</button>
      </form>
      {error && <p className="error">{error}</p>}
      {loading && data && (
        <p className="loading">
          Checked {data.done} of {data.total || '…'}
        </p>
      )}

      {data && (
        <section id="results">
          <h2>Vendors</h2>
          <p className="muted intro">
            Checked {data.vendors} vendor websites. Only shops with a searchable online store can show
            up here, so browse the vendor list below for the rest.
          </p>
          {!loading && data.hits.length === 0 && <p className="muted">No vendor websites matched.</p>}
          {data.hits.map((h) => (
            <div className="card" key={h.vendor.id}>
              <h3>
                {h.vendor.name} <span className="tag">{h.vendor.kind}</span>
              </h3>
              <div className="body">
                <p className="muted">
                  {h.vendor.minutes} min · {h.vendor.address}
                </p>
                <Products products={h.products} />
                <a className="small" href={h.search_url} target="_blank" rel="noreferrer">
                  Open their search ↗
                </a>
              </div>
            </div>
          ))}

          <h2>Online shops</h2>
          {data.sources.map((r) => (
            <div className="card" key={r.source}>
              <h3>{r.source}</h3>
              <div className="body">
                {r.ok && r.products.length === 0 && <p className="muted">No matches found.</p>}
                {!r.ok && (
                  <p className="muted">
                    Could not check this shop right now.
                  </p>
                )}
                <Products products={r.products} />
                <a className="small" href={r.search_url} target="_blank" rel="noreferrer">
                  Open {r.source} search ↗
                </a>
              </div>
            </div>
          ))}
        </section>
      )}

      <section id="vendors">
        <h2>Nearby</h2>
        {vendorError && <p className="error">{vendorError}</p>}
        {!vendors && !vendorError && (
          <p className="muted">
            Loading vendors. The first run downloads them from OpenStreetMap and can take a few minutes.
          </p>
        )}
        {vendors && (
          <>
            <p className="muted intro">
              {visible.length} of {vendors.length} shown. Source: OpenStreetMap, so some places may be missing or out of
              date. Call ahead.
            </p>
            <div className="chips">
              {kinds.map((k) => (
                <button
                  type="button"
                  key={k}
                  className={'chip' + (k === kind ? ' on' : '')}
                  onClick={() => {
                    setKind(k)
                    setShown(PAGE)
                  }}
                >
                  {k}
                </button>
              ))}
            </div>
            <input
              className="filter"
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value)
                setShown(PAGE)
              }}
              placeholder="Filter by name or place"
            />
            {visible.slice(0, shown).map((v) => (
              <VendorRow key={v.id} v={v} />
            ))}
            {shown < visible.length && (
              <button type="button" className="more" onClick={() => setShown(shown + PAGE)}>
                Show more
              </button>
            )}
          </>
        )}
      </section>

    </div>
  )
}
