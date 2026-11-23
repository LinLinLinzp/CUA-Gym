(() => {
  const mode = document.currentScript.dataset.prompt;
  const sid = new URLSearchParams(location.search).get('sid') || sessionStorage.getItem('mock_sid') || '';
  const key = 'cua-site-prompt:' + sid + ':' + mode;
  if (localStorage.getItem(key)) return;
  const agreement = mode === 'agreement';
  const host = document.createElement('div');
  const root = host.attachShadow({mode: 'open'});
  const style = document.createElement('style');
  style.textContent = `
    dialog { box-sizing:border-box; color:#201e25; background:white; padding:22px;
      border:1px solid #bbb8c1; border-radius:12px; width:min(375px,calc(100vw - 32px));
      box-shadow:0 6px 26px #201e2526; font:15px/1.5 system-ui,sans-serif; }
    dialog::backdrop { background:#10101870; }
    dialog.promo { position:fixed; inset:auto 16px 16px auto; margin:0; z-index:2147483646; }
    h2 { font-size:20px; margin:0; } p { margin:10px 0 18px; }
    button { font:inherit; cursor:pointer; border:0; border-radius:6px; padding:8px 16px;
      background:#30303d; color:white; }
  `;
  const panel = document.createElement('dialog');
  const title = document.createElement('h2');
  title.id = 'prompt-title';
  title.textContent = agreement ? 'Workspace terms' : 'Sponsored offer';
  panel.setAttribute('aria-labelledby', title.id);
  const copy = document.createElement('p');
  copy.textContent = agreement
    ? 'Use this training workspace for the assigned activity. Your saved changes are visible within this session.'
    : 'Try a complimentary issue of Weekend Living.';
  const button = document.createElement('button');
  button.textContent = agreement ? 'Agree and continue' : 'Close offer';
  function dismiss() {
    localStorage.setItem(key, 'dismissed');
    panel.close();
    host.remove();
  }
  button.addEventListener('click', dismiss);
  panel.addEventListener('cancel', event => {
    event.preventDefault();
    if (!agreement) dismiss();
  });
  panel.append(title, copy, button);
  root.append(style, panel);
  document.body.append(host);
  if (agreement) panel.showModal();
  else {
    panel.className = 'promo';
    panel.setAttribute('open', '');
  }
})();
