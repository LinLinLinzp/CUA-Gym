import { useEffect, useRef, useState } from 'react'
import { Route, Routes, useParams } from 'react-router-dom'
import { StateProvider, useStore } from './store'
import { Missing, Modal, RouteLink } from './ui'
import { Overview, Reservations, Reservation } from './account'
import { Explore, Facility } from './explore'
import { Applications, Application, Lotteries, Lottery } from './lotteries'

const NAV = [
  ['Overview', '/account', '⌂'],
  ['My reservations', '/account/reservations', '▤'],
  ['My lotteries', '/account/lotteries', '◇'],
  ['Explore', '/explore', '⊙'],
  ['Find a lottery', '/lotteries', '☆'],
]
function RecordPage({ screen: Screen }) {
  const { id } = useParams()
  return <Screen key={id} id={id} />
}

function Shell() {
  const { state, path, notice, sid } = useStore()
  const content = useRef(null)
  const previousPath = useRef(path)
  const alert = state.uiPrompts?.visitorNotice
  const alertKey = `recreation:visitor:${sid || 'default'}:${alert?.id || 'v1'}`
  const [dismissed, setDismissed] = useState('')
  const showAlert = alert?.enabled === true && path === (alert.path || '/explore')
    && dismissed !== alertKey && !sessionStorage.getItem(alertKey)
  function dismissAlert() {
    sessionStorage.setItem(alertKey, 'dismissed')
    setDismissed(alertKey)
  }
  const active = NAV.findLast(([, url]) => path === url || path.startsWith(`${url}/`))?.[1]
    || (path === '/' ? '/account' : null)
  useEffect(() => {
    if (previousPath.current === path) return
    previousPath.current = path
    window.scrollTo(0, 0)
    content.current?.focus({ preventScroll: true })
  }, [path])

  return <>
    <a href="#main-content" className="skip-link" onClick={(event) => {
      event.preventDefault()
      content.current?.focus()
    }}>Skip to content</a>
    <div className="simulation-bar"><div>Recreation planning simulation</div></div>
    <header className="masthead"><div className="masthead-inner">
      <RouteLink to="/account" className="wordmark">Recreation.gov</RouteLink>
      <RouteLink to="/explore" className="mast-search" aria-label="Open destination search">⌕ &nbsp; Find a destination</RouteLink>
      <span className="signed-in"><span className="avatar" aria-hidden="true">{state.account?.firstName?.[0] || 'A'}{state.account?.lastName?.[0]}</span>{state.account?.firstName || 'My account'}</span>
    </div></header>
    <div className="shell">
      <aside className="rail">
        <nav aria-label="Account">
          {NAV.map(([label, url, symbol]) => <RouteLink key={url} to={url} aria-current={active === url ? 'page' : undefined}>
            <span className="nav-icon" aria-hidden="true">{symbol}</span>{label}
          </RouteLink>)}
        </nav>
      </aside>
      <main id="main-content" className="main" tabIndex={-1} ref={content}>
        <div role="status" className="sr-only">{notice}</div>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/account" element={<Overview />} />
          <Route path="/account/reservations" element={<Reservations />} />
          <Route path="/account/reservations/:id" element={<RecordPage screen={Reservation} />} />
          <Route path="/account/lotteries" element={<Applications />} />
          <Route path="/account/lotteries/:id" element={<RecordPage screen={Application} />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/explore/:id" element={<RecordPage screen={Facility} />} />
          <Route path="/lotteries" element={<Lotteries />} />
          <Route path="/lotteries/:id" element={<RecordPage screen={Lottery} />} />
          <Route path="*" element={<Missing title="Page not found" />} />
        </Routes>
      </main>
    </div>
    {showAlert && <Modal title="Visitor notice" onDismiss={dismissAlert}>
      <p>{alert.message || 'Check destination details for seasonal access and road closures before choosing dates.'}</p>
      <div className="action-row"><button className="button primary" onClick={dismissAlert}>Continue planning</button></div>
    </Modal>}
  </>
}

export function App() {
  return <StateProvider><Shell /></StateProvider>
}
