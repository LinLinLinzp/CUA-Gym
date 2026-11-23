import { loadState, saveState } from './utils/dataManager.js'
import { createInitialData } from './data/seed.js'
import './style.css'

async function start() {
  const state = await loadState('bibliocommons_mock', createInitialData)
  // Earlier browser sessions cached the original pilot without borrowing or shelf fields.
  state.checkouts ??= createInitialData().checkouts
  state.forLater ??= []
  const app = document.querySelector('#app')
  app.innerHTML = `
    <header><div class="utility"><div class="wrap"><span>◎ English</span><details class="account-menu"><summary>My SFPL</summary><div><a href="#checkouts">Checked Out</a><a href="#holds">On Hold</a><a href="#later">For Later Shelf</a></div></details></div></div>
    <div class="mast-band"><div class="wrap mast"><img src="/images/logo.png" alt="San Francisco Public Library">
      <form id="search" role="search"><label for="query">Search the <span>Catalog</span> by</label><select id="field" aria-label="Search by"><option>Keyword</option><option>Title</option><option>Author</option></select>
      <input id="query" type="search" name="q" value="botany"><button aria-label="Search">⌕</button></form></div></div>
    <nav><div class="wrap"><a href="#catalog">Books &amp; Media</a><a href="#holds">On Hold</a><a href="#checkouts">Checked Out</a><a href="#later">For Later Shelf</a></div></nav></header>
    <main class="wrap"><h1></h1><div class="subnav"></div><div class="columns"><aside></aside><section aria-label="Results"><div class="result-tools"><label id="sort-label">Sort by: <select id="sort"><option value="default">Relevance</option><option value="author">Author</option><option value="title">Title</option></select></label><div class="views" aria-label="Results view"><button type="button" data-view="list" aria-label="List view" title="List view">☰</button><button type="button" data-view="covers" aria-label="Cover view" title="Cover view">▦</button><button type="button" data-view="grouped" aria-label="Grouped results view" title="Grouped results view">▤</button></div><span id="summary"></span></div><div id="results"></div></section></div></main>
    <dialog><form id="request"><h2>Place hold</h2><p id="hold-title"></p><label for="branch">Pickup location</label>
    <select id="branch" name="branch" required></select><footer><button type="button" id="cancel">Cancel</button><button class="primary">Confirm hold</button></footer></form></dialog>
    <p role="status" class="status"></p>`
  const results = app.querySelector('#results')
  const query = app.querySelector('#query')
  const dialog = app.querySelector('dialog')
  const branch = app.querySelector('#branch')
  const aside = app.querySelector('aside')
  let filterAvailable = false
  let selectedId
  let term = query.value
  let view = 'grouped'
  let format = ''
  let field = 'Keyword'
  function save(message) {
    saveState('bibliocommons_mock', state)
    render()
    app.querySelector('.status').textContent = message
  }
  function action(parent, label, onClick, primary = false) {
    const button = document.createElement('button')
    button.textContent = label
    if (primary) button.className = 'primary'
    button.onclick = onClick
    parent.append(button)
  }
  function openHold(title) {
    selectedId = title.id
    app.querySelector('#hold-title').textContent = [title.title, title.format, title.year].filter(Boolean).join(' · ')
    branch.replaceChildren(...state.branches.map(place => new Option(place.name, place.id)))
    dialog.showModal()
  }
  function render() {
    const account = location.hash === '#holds'
    const loans = location.hash === '#checkouts'
    const shelf = location.hash === '#later'
    const catalog = !account && !loans && !shelf
    const heading = app.querySelector('h1')
    heading.textContent = account ? 'On Hold' : loans ? 'Checked Out' : shelf ? 'For Later Shelf' : field + ' search: '
    results.dataset.view = catalog ? view : 'grouped'
    app.querySelector('.views').hidden = !catalog
    for (const b of app.querySelectorAll('.views button')) b.setAttribute('aria-pressed', String(view === b.dataset.view))
    if (catalog) {
      const strong = document.createElement('strong')
      strong.textContent = term || 'All titles'
      heading.append(strong)
    }
    app.querySelector('.subnav').textContent = catalog ? 'Catalog search results' : 'My SFPL  ›  ' + (shelf ? 'My Collections' : 'My Borrowing')
    app.querySelector('#sort-label').hidden = !catalog
    aside.innerHTML = catalog ? '<details open><summary>Available at</summary><label><input type="checkbox" id="available"> Available titles</label></details><details open><summary>Format</summary><b>Books</b><label><input name="format" type="checkbox" value="Book"> Book</label><label><input name="format" type="checkbox" value="eBook"> eBook</label></details>' : '<h2>My Borrowing</h2><a href="#checkouts">Checked Out</a><a href="#holds">On Hold</a><h2>My Collections</h2><a href="#later">For Later Shelf</a>'
    if (catalog) {
      for (const facet of aside.querySelectorAll('[name=format]')) {
        facet.checked = format === facet.value
        facet.onchange = () => { format = facet.checked ? facet.value : ''; render() }
      }
      const filter = aside.querySelector('input')
      filter.checked = filterAvailable
      filter.onchange = () => { filterAvailable = filter.checked; render() }
    }
    results.replaceChildren()
    if (loans) {
      const checkouts = [...state.checkouts].sort((a,b) => String(a.dueDate).localeCompare(String(b.dueDate)))
      app.querySelector('#summary').textContent = checkouts.length + ' checked out'
      for (const loan of checkouts) {
        const row = document.createElement('article')
        row.className = 'loan'
        row.innerHTML = '<div class="book"><h2></h2><p class="author"></p><small></small></div><div class="transaction"><strong></strong></div>'
        row.querySelector('h2').textContent = loan.title
        row.querySelector('.author').textContent = loan.author
        row.querySelector('small').textContent = loan.format
        const transaction = row.querySelector('.transaction')
        transaction.querySelector('strong').textContent = 'Due ' + loan.dueDate
        action(transaction, 'Renew', () => {
          const next = loan.renewalDates?.[loan.renewals || 0]
          if (loan.renewalBlock || !next) {
            app.querySelector('.status').textContent = loan.title + ' — ' + (loan.renewalBlock || 'Renewal limit reached.')
            return
          }
          loan.dueDate = next
          loan.renewals = (loan.renewals || 0) + 1
          loan.renewedAt = new Date().toISOString()
          save('Renewed. ' + loan.title + ' is due ' + next + '.')
        })
        results.append(row)
      }
      return
    }
    const titles = state.titles.filter(title => {
      if (shelf) return state.forLater.includes(title.id)
      const data = field === 'Title' ? title.title : field === 'Author' ? title.author : [title.title, title.author].join(' ')
      return String(data || '').toLowerCase().includes(term.toLowerCase()) && (!filterAvailable || title.canHold) && (!format || title.format === format)
    })
    const sort = app.querySelector('#sort').value
    if (catalog && sort !== 'default') titles.sort((a,b) => String(a[sort]).localeCompare(String(b[sort])))
    const rows = account ? state.holds.map(hold => ({ hold, title: state.titles.find(t => t.id === hold.titleId) })) : titles.map(title => ({ title, hold: state.holds.find(h => h.titleId === title.id) }))
    const unit = account ? 'hold' : 'result'
    app.querySelector('#summary').textContent = rows.length + ' ' + unit + (rows.length === 1 ? '' : 's')
    for (const { title, hold } of rows) {
      if (!title) continue
      const row = document.createElement('article')
      row.innerHTML = '<div class="jacket"></div><div class="record"><div class="book"><h2></h2><p class="author"></p></div><div class="holding"><div class="metadata"><p class="edition"></p><small></small><strong></strong></div><div class="transaction"></div></div></div>'
      if (['botany.jpg', 'botany-kovacs.jpg'].includes(title.cover)) {
        const img = document.createElement('img')
        img.alt = 'Cover of ' + title.title
        img.src = '/images/' + title.cover
        row.querySelector('.jacket').append(img)
      } else { row.querySelector('.jacket').textContent = title.format }
      row.querySelector('h2').textContent = title.title
      row.querySelector('.author').textContent = 'by ' + (title.author || '')
      row.querySelector('.edition').textContent = [title.format, title.year, title.edition].filter(Boolean).join(' · ')
      row.querySelector('small').textContent = title.callNumber || ''
      const transaction = row.querySelector('.transaction')
      row.querySelector('.metadata strong').textContent = hold ? ({ paused: 'Paused', ready: 'Ready for pickup' }[hold.status] || 'On hold') : title.availability
      if (account) {
        const pickup = document.createElement('p')
        pickup.textContent = 'Pickup location: ' + (state.branches.find(p => p.id === hold.branchId)?.name || hold.branchId)
        transaction.append(pickup)
        if (hold.status === 'active' || hold.status === 'paused') {
          action(transaction, hold.status === 'active' ? 'Pause hold' : 'Resume hold', () => {
            hold.status = hold.status === 'active' ? 'paused' : 'active'
            hold.updatedAt = new Date().toISOString()
            save(hold.status === 'paused' ? 'Hold paused.' : 'Hold resumed.')
          })
        }
      } else if (title.canHold && !hold && state.branches.length) {
        const button = document.createElement('button')
        button.className = 'primary'
        button.textContent = 'Place hold'
        button.onclick = () => openHold(title)
        transaction.append(button)
      }
      if (!account) {
        const saved = state.forLater.includes(title.id)
        action(transaction, saved ? 'Remove from For Later' : 'For Later', () => {
          if (saved) state.forLater = state.forLater.filter(id => id !== title.id)
          else state.forLater.push(title.id)
          save(saved ? 'Removed from your shelf.' : 'Added to your For Later shelf.')
        })
      }
      results.append(row)
    }
  }
  for (const button of app.querySelectorAll('.views button')) {
    button.onclick = () => { view = button.dataset.view; render() }
  }
  app.querySelector('#sort').onchange = render
  app.querySelector('#search').onsubmit = event => {
    event.preventDefault()
    field = app.querySelector('#field').value
    term = query.value.trim()
    location.hash = 'catalog'
    render()
  }
  app.querySelector('#cancel').onclick = () => dialog.close()
  app.querySelector('#request').onsubmit = event => {
    event.preventDefault()
    if (!state.branches.some(b => b.id === branch.value) || state.holds.some(h => h.titleId === selectedId)) return
    state.holds.push({ id: crypto.randomUUID(), titleId: selectedId, branchId: branch.value, status: 'active', createdAt: new Date().toISOString() })
    saveState('bibliocommons_mock', state)
    dialog.close()
    render()
    app.querySelector('.status').textContent = 'Hold placed.'
  }
  window.addEventListener('hashchange', () => {
    app.querySelector('.account-menu').open = false
    app.querySelector('.status').textContent = ''
    render()
  })
  render()
}
start()
