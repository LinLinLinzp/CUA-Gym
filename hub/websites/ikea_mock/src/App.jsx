import React, { useState } from 'react'
import { ArrowUpRight, Armchair, ChevronRight, ClipboardList, House, PackageOpen, Search, ShoppingBag, Truck, UserRound } from 'lucide-react'
import { Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { useAccount } from './store.jsx'
import { AccountLink, detailPath, Empty, OrderRow, Page, useAccountNavigate } from './components.jsx'
import { future, list, newest, orderLabel, serviceLabel, slotText, statusLabel } from './utils/account.js'
import { Cart, Catalog, Checkout } from './pages/Shopping.jsx'
import { OrderDetail, Orders } from './pages/Orders.jsx'
import { ReturnDetail, ReturnForm, Returns } from './pages/Returns.jsx'
import { getSessionId } from './utils/dataManager.js'
import { ServiceDetail, Services } from './pages/Services.jsx'

const navigation = [
  ['/', 'Overview', House], ['/products', 'Products', Armchair], ['/cart', 'Cart', ShoppingBag],
  ['/orders', 'Purchases', ClipboardList], ['/services', 'Delivery & assembly', Truck], ['/returns', 'Returns', PackageOpen],
]

function quantity(cart) {
  return list(cart?.lines).reduce((sum, line) => sum + (Number(line.quantity) || 0), 0)
}

function PrivacyNotice() {
  const { state } = useAccount()
  const { pathname } = useLocation()
  const settings = state.uiPrompts?.privacy
  const key = `ikea:privacy:${getSessionId() || 'default'}:${settings?.id || 'v1'}`
  const [dismissed, setDismissed] = useState('')
  const [choices, setChoices] = useState(false)
  if (settings?.enabled !== true || (settings.path && settings.path !== pathname)
    || dismissed === key || sessionStorage.getItem(key)) return null

  function save(choice) {
    sessionStorage.setItem(key, choice)
    setDismissed(key)
    setChoices(false)
  }
  return <section className="privacy-notice" aria-labelledby="privacy-title">
    <h2 id="privacy-title">Cookie preferences</h2>
    {choices ? <form onSubmit={(event) => {
      event.preventDefault()
      save(event.currentTarget.elements.optional.checked ? 'optional' : 'essential')
    }}>
      <p>Essential storage keeps your cart and account available.</p>
      <label><input name="optional" type="checkbox" /> Allow optional storage</label>
      <div className="privacy-actions"><button className="button primary">Save preferences</button>
        <button type="button" className="button" onClick={() => setChoices(false)}>Back</button></div>
    </form> : <>
      <p>This shopping simulation uses essential browser storage. Your choice applies to this browser session.</p>
      <div className="privacy-actions"><button className="button primary" onClick={() => save('optional')}>Allow optional</button>
        <button className="button" onClick={() => setChoices(true)}>Choose settings</button></div>
    </>}
  </section>
}

function Shell() {
  const { state } = useAccount()
  const itemCount = quantity(state.cart)
  const { pathname } = useLocation()
  const navigate = useAccountNavigate()
  return <>
    <header className="site-header">
      <div className="utility-bar"><div><span>US · English</span><AccountLink to="/services">Delivery and assembly help</AccountLink></div></div>
      <div className="header-inner">
        <AccountLink to="/" className="wordmark" aria-label="IKEA account home">IKEA</AccountLink>
        <span className="account-context">Customer account <small>Simulation</small></span>
        <form className="header-find" role="search" onSubmit={(event) => {
          event.preventDefault()
          const query = new FormData(event.currentTarget).get('order').trim()
          navigate(query ? '/orders?' + new URLSearchParams({ q: query }) : '/orders')
        }}>
          <label className="sr-only" htmlFor="header-order">Find an order</label>
          <input id="header-order" type="search" name="order" placeholder="Order number or item" />
          <button type="submit" aria-label="Run order search"><Search size={18} aria-hidden="true" /></button>
        </form>
        <div className="header-actions">
          <AccountLink to="/cart" className="header-cart" aria-label={'Cart, ' + itemCount + (itemCount === 1 ? ' item' : ' items')}>
            <ShoppingBag size={20} aria-hidden="true" /> <span>Cart</span><strong>{itemCount}</strong>
          </AccountLink>
          <div className="profile"><span className="avatar"><UserRound size={18} aria-hidden="true" /></span>
            <span>{state.profile?.name || 'Your account'}</span></div>
        </div>
      </div>
    </header>
    <div className={pathname === "/" ? "workspace workspace-overview" : "workspace"}>
      <aside className="rail">
        <nav aria-label="Account navigation">
          <p className="rail-title">Your account</p>
          {navigation.map(([to, label, Icon]) => <AccountLink key={to} to={to} nav end={to === '/'}
            className={({ isActive }) => 'rail-link' + (isActive ? ' active' : '')}>
            <Icon size={19} strokeWidth={1.75} aria-hidden="true" /> {label}
          </AccountLink>)}
        </nav>
      </aside>
      <main className="content" id="main"><Outlet /></main>
    </div>
    <PrivacyNotice />
  </>
}

function Overview() {
  const { state } = useAccount()
  const firstName = state.profile?.name?.trim()?.split(/\s+/)[0]
  const nextBooking = list(state.bookings).filter((booking) => booking.status === 'scheduled' && future(booking.slot?.startsAt))
    .sort((a, b) => Date.parse(a.slot.startsAt) - Date.parse(b.slot.startsAt))[0]
  const latestReturn = newest(state.returns)[0]
  const recentOrders = newest(state.orders).slice(0, 3)
  const itemCount = quantity(state.cart)
  const shortcuts = [
    ['/cart', 'Your cart', itemCount ? itemCount + (itemCount === 1 ? ' item ready to review' : ' items ready to review') : 'Your cart is empty', ShoppingBag],
    ['/services', 'Delivery & assembly', nextBooking ? serviceLabel(nextBooking.type) + ' · ' + slotText(nextBooking.slot) : 'No upcoming appointments', Truck],
    ['/returns', 'Returns', latestReturn ? (latestReturn.reference || latestReturn.id) + ' · ' + statusLabel(latestReturn.status) : 'No return requests yet', PackageOpen],
  ]
  return <div className="stack">
    <section className="account-service-overview" aria-labelledby="order-services-title">
      <p className="account-crumb">Customer account / Order services</p>
      <h1>{firstName ? 'Hi, ' + firstName + '.' : 'Your account'}</h1>
      <h2 id="order-services-title">Manage your orders</h2>
      <div className="account-intro">
        <div className="order-service-main">
          <p>Find receipts, check delivery status or make changes to an existing purchase.</p>
          <div className="overview-actions">
            {recentOrders[0] && <AccountLink to={detailPath('orders', recentOrders[0].id)} className="button primary">View latest order <ArrowUpRight size={16} aria-hidden="true" /></AccountLink>}
            <AccountLink className="button secondary" to="/orders">View purchases</AccountLink>
          </div>
          {recentOrders[0] && <p className="latest-status">Latest order <strong>{orderLabel(recentOrders[0])}</strong><span>{statusLabel(recentOrders[0].status)}</span></p>}
        </div>
        <section aria-label="Account shortcuts" className="order-services"><h3>Account services</h3>
          {shortcuts.map(([to, title, description, Icon]) => <AccountLink key={to} to={to} className="shortcut">
            <span className="tile-icon"><Icon size={21} aria-hidden="true" /></span>
            <span className="shortcut-title">{title}</span>
            <span className="muted shortcut-description">{description}</span>
            <ChevronRight className="shortcut-arrow" size={19} aria-hidden="true" />
          </AccountLink>)}
        </section>
      </div>
    </section>
    <section>
      <div className="section-heading"><h2>Recent purchases</h2><AccountLink to="/orders">All purchases <ChevronRight size={16} aria-hidden="true" /></AccountLink></div>
      {recentOrders.length ? <div className="card rows">{recentOrders.map((order) =>
        <OrderRow key={order.id} order={order} showPhoto={false} />)}
      </div> : <Empty title="No purchases yet" action={<AccountLink to="/products">Browse products</AccountLink>} />}
    </section>
  </div>
}

function NotFound() {
  return <Page title="Page unavailable"><Empty title="This page couldn’t be found" action={<AccountLink to="/">Back to overview</AccountLink>} /></Page>
}

export function App() {
  return <Routes>
    <Route element={<Shell />}>
      <Route index element={<Overview />} />
      <Route path="products" element={<Catalog />} />
      <Route path="cart" element={<Cart />} />
      <Route path="checkout" element={<Checkout />} />
      <Route path="orders" element={<Orders />} />
      <Route path="orders/:orderId" element={<OrderDetail />} />
      <Route path="services" element={<Services />} />
      <Route path="services/:bookingId" element={<ServiceDetail />} />
      <Route path="returns" element={<Returns />} />
      <Route path="returns/new" element={<ReturnForm />} />
      <Route path="returns/:returnId" element={<ReturnDetail />} />
      <Route path="*" element={<NotFound />} />
    </Route>
  </Routes>
}
