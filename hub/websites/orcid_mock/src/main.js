import { loadState, saveState } from './utils/dataManager.js'
import { createInitialData } from './data/seed.js'
import './style.css'

async function start() {
  const state = await loadState('orcid_mock', createInitialData)
  const app = document.querySelector('#app')
  app.innerHTML = `
    <header><div class="bar"><img src="/images/logo.png" alt="ORCID"><span>My ORCID record</span><strong class="name"></strong></div></header>
    <main><aside><p class="eyebrow">ORCID RECORD</p><h1 class="name"></h1><hr><h3>Personal information</h3><a href="#works">Works</a></aside>
    <section id="works"><div class="workbar"><h2><button type="button" id="toggle-works" aria-expanded="true" aria-controls="works-list">Works <span id="count"></span></button></h2><button id="add" aria-label="+ Add" aria-expanded="false" aria-controls="manual"><b aria-hidden="true">⊕</b> Add</button><label class="sort">Sort <select aria-label="Sort works"><option value="record">Record order</option><option value="title">Title</option><option value="year">Year</option></select></label></div>
    <button id="manual" hidden>Add work manually<small>Enter the work details yourself</small></button>
    <div class="selection"><label><input type="checkbox" id="all"> Select all</label><span id="selected-count"></span><label>Actions <select id="bulk" aria-label="Change selected works visibility"><option value="">Change visibility</option><option>Everyone</option><option>Trusted parties</option><option>Only me</option></select></label></div>
    <div id="works-list"></div><p class="notice" role="status"></p></section></main>
    <dialog aria-labelledby="form-title"><form><h2 id="form-title">Add work manually</h2><h3 class="subhead">Work details</h3><label>Work type<select name="type"><option>Journal article</option><option>Book</option><option>Dataset</option></select></label>
    <label>Work title <span aria-hidden="true">*</span><input name="title" required maxlength="500"></label>
    <label>Publication year<input name="year" inputmode="numeric" pattern="[0-9]{4}" maxlength="4"></label>
    <h3 class="subhead">Visibility</h3><p class="visibility-help">Your default visibility is <strong></strong>.</p><label class="visibility-field"><select name="visibility" aria-label="Visibility"><option>Everyone</option><option>Trusted parties</option><option>Only me</option></select></label>
    <footer><button class="primary">Save changes</button><button type="button" class="cancel">Cancel</button></footer></form></dialog>`
  app.querySelectorAll('.name').forEach(el => { el.textContent = state.researcher.name })
  const dialog = app.querySelector('dialog')
  const form = dialog.querySelector('form')
  const add = app.querySelector('#add')
  const manual = app.querySelector('#manual')
  const selected = new Set()
  const bulk = app.querySelector('#bulk')
  const all = app.querySelector('#all')
  const sort = app.querySelector('.sort select')
  let editing = null
  function editable(work) {
    return work.sourceKind ? work.sourceKind === 'self' : Boolean(work.source && work.source === state.researcher.name)
  }
  function syncSelection() {
    all.checked = state.works.length > 0 && selected.size === state.works.length
    all.indeterminate = selected.size > 0 && !all.checked
    bulk.disabled = !selected.size
    app.querySelector('#selected-count').textContent = 'Items currently selected (' + selected.size + ')'
  }
  all.onchange = () => {
    selected.clear()
    if (all.checked) state.works.forEach(work => selected.add(work.id))
    render()
  }
  bulk.onchange = () => {
    if (!bulk.value) return
    for (const work of state.works) if (selected.has(work.id)) work.visibility = bulk.value
    saveState('orcid_mock', state)
    bulk.value = ''
    render()
  }
  const toggle = app.querySelector('#toggle-works')
  toggle.onclick = () => {
    const expanded = toggle.getAttribute('aria-expanded') !== 'true'
    toggle.setAttribute('aria-expanded', String(expanded))
    app.querySelector('#works-list').hidden = !expanded
    app.querySelector('.selection').hidden = !expanded
  }
  sort.onchange = () => render()
  function render() {
    const list = app.querySelector('#works-list')
    list.replaceChildren()
    app.querySelector('#count').textContent = '(' + state.works.length + ')'
    syncSelection()
    const works = [...state.works]
    if (sort.value === 'title') works.sort((a, b) => String(a.title).localeCompare(String(b.title)))
    if (sort.value === 'year') works.sort((a, b) => Number(b.year || 0) - Number(a.year || 0))
    for (const work of works) {
      const card = document.createElement('article')
      const title = document.createElement('h3')
      title.textContent = work.title
      const details = document.createElement('p')
      details.textContent = [work.year, work.type].filter(Boolean).join('  |  ')
      const source = document.createElement('small')
      const sourceLabel = document.createElement('b')
      sourceLabel.textContent = 'Source: '
      const sourceIcon = document.createElement('span')
      sourceIcon.setAttribute('aria-hidden', 'true')
      sourceIcon.className = 'source-icon'
      sourceIcon.textContent = editable(work) ? '●' : '▦'
      source.append(sourceLabel, sourceIcon, document.createTextNode(work.source || 'Unknown'))
      const head = document.createElement('div')
      head.className = 'workhead'
      const pick = document.createElement('input')
      pick.type = 'checkbox'
      pick.checked = selected.has(work.id)
      pick.setAttribute('aria-label', 'Select ' + work.title)
      pick.onchange = () => { if (pick.checked) selected.add(work.id); else selected.delete(work.id); syncSelection() }
      const visibility = document.createElement('select')
      visibility.setAttribute('aria-label', 'Visibility for ' + work.title)
      visibility.replaceChildren(...['Everyone', 'Trusted parties', 'Only me'].map(v => new Option(v, v)))
      visibility.value = work.visibility || state.researcher.defaultVisibility
      visibility.onchange = () => { work.visibility = visibility.value; privacy.dataset.level = visibility.value; saveState('orcid_mock', state) }
      visibility.className = 'visibility'
      const privacy = document.createElement('label')
      privacy.className = 'privacy-control'
      privacy.dataset.level = visibility.value
      privacy.append(visibility)
      head.append(pick, title, privacy)
      if (editable(work)) {
        const edit = document.createElement('button')
        edit.className = 'edit'
        edit.textContent = '✎'
        edit.setAttribute('aria-label', 'Edit ' + work.title)
        edit.onclick = () => openForm(work)
        head.append(edit)
      }
      const sourceRow = document.createElement('div')
      sourceRow.className = 'source-row'
      sourceRow.append(source)
      card.append(head, details, sourceRow)
      list.append(card)
    }
  }
  add.onclick = () => {
    manual.hidden = !manual.hidden
    add.setAttribute('aria-expanded', String(!manual.hidden))
  }
  function openForm(work = null) {
    editing = work
    manual.hidden = true
    add.setAttribute('aria-expanded', 'false')
    form.reset()
    form.querySelector('.visibility-help strong').textContent = state.researcher.defaultVisibility || 'Everyone'
    form.querySelector('h2').textContent = work ? 'Edit work' : 'Add work manually'
    if (work) {
      for (const key of ['type','title','year']) {
        if (key === 'type' && work.type && !Array.from(form.elements.type.options).some(o => o.value === work.type)) form.elements.type.add(new Option(work.type))
        form.elements[key].value = work[key] ?? ''
      }
    }
    form.elements.visibility.value = work?.visibility || state.researcher.defaultVisibility || 'Everyone'
    if (toggle.getAttribute('aria-expanded') === 'false') toggle.click()
    dialog.showModal()
  }
  manual.onclick = () => openForm()
  form.querySelector('.cancel').onclick = () => dialog.close()
  dialog.onclose = () => add.focus()
  form.onsubmit = event => {
    event.preventDefault()
    const fields = Object.fromEntries(new FormData(form))
    fields.title = fields.title.trim()
    if (!fields.title) { form.elements.title.focus(); return }
    if (editing) {
      if (!editable(editing)) return
      Object.assign(editing, fields, { updatedAt: new Date().toISOString() })
    } else {
      state.works.unshift({ ...fields, id: crypto.randomUUID(), source: state.researcher.name, sourceKind: 'self', createdAt: new Date().toISOString() })
    }
    saveState('orcid_mock', state)
    dialog.close()
    render()
    app.querySelector('.notice').textContent = editing ? 'Work updated.' : 'Work added to your record.'
  }
  render()
}
start()
