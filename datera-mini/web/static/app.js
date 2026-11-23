// DATERA EDU mini: single-page client. Plain JavaScript, no build step.

const $ = (s, root = document) => root.querySelector(s);
const e = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const fdate = (iso) => { if (!iso) return 'нет'; const [, m, d] = iso.split('-'); return `${+d} ${MONTHS[+m - 1]}`; };
const tc = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const mins = (s) => (s == null ? '' : `${Math.max(1, Math.round(s / 60))} мин`);
const plural = (n, one, few, many) => { const a = n % 10, b = n % 100; return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 10 || b >= 20) ? few : many; };
const initials = (n) => n.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();

const ic = (d, size = 16) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const I = {
  users: ic('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>'),
  lessons: ic('<circle cx="12" cy="12" r="10"/><path d="m10 8 6 4-6 4z"/>'),
  book: ic('<path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2zM22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/>'),
  upload: ic('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>'),
  map: ic('<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15M15 6v15"/>'),
  team: ic('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/>'),
  settings: ic('<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>'),
  logout: ic('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>'),
  check: ic('<path d="M20 6 9 17l-5-5"/>'),
  x: ic('<path d="M18 6 6 18M6 6l12 12"/>'),
  edit: ic('<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>', 14),
  doc: ic('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h6"/>', 14),
  info: ic('<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>'),
  plus: ic('<path d="M12 5v14M5 12h14"/>'),
  dash: ic('<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>'),
  play: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M7 4v16l13-8z"/></svg>',
  pause: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>',
  tri: '<svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><path d="M6 3v18l15-9z"/></svg>',
  chip: ic('<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 9h6v6H9zM9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4"/>', 14),
  logo: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"><path d="M6 9v6M10 5v14M14 8v8M18 10v4"/></svg>',
};

let me = null;
let pollTimer = null;
let audio = null;

async function api(path, opts = {}) {
  if (opts.json) { opts.body = JSON.stringify(opts.json); opts.headers = { 'Content-Type': 'application/json' }; opts.method = opts.method || 'POST'; }
  const r = await fetch('/api' + path, opts);
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && me) { me = null; location.hash = ''; route(); }
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Ошибка запроса');
  return data;
}

function toast(text) {
  $('#toast').innerHTML = `<div>${I.check} ${e(text)}</div>`;
  setTimeout(() => { $('#toast').innerHTML = ''; }, 2600);
}
const closeModal = () => { $('#modal').innerHTML = ''; };
const modal = (html) => { $('#modal').innerHTML = `<div class="overlay" data-act="overlay"><div class="dialog">${html}</div></div>`; };

const pill = (color, label) => `<span class="pill ${color}"><i class="dot c-${color}"></i>${e(label)}</span>`;
const bar = (idx, color) => `<span class="bar"><i class="c-${color}" style="width:${idx ?? 0}%"></i></span>`;
const crumbs = (items) => `<div class="crumbs">${items.map((c) => (c[1] ? `<a href="${c[1]}">${e(c[0])}</a>` : e(c[0]))).join('<i>/</i>')}</div>`;

// ---------------------------------------------------------------- shell

const NAV = {
  teacher: [['#/overview', 'Обзор', I.dash], ['#/students', 'Ученики', I.users], ['#/parents', 'Родители', I.team], ['#/lessons', 'Уроки', I.lessons], ['#/subjects', 'Предметы и материалы', I.book], ['#/whisper', 'Проверка Whisper', I.chip]],
  student: [['#/home', 'Мои уроки', I.lessons], ['#/map', 'Карта знаний', I.map], ['#/profile', 'Профиль', I.settings]],
  parent: [['#/home', 'Уроки ребёнка', I.lessons], ['#/map', 'Карта знаний', I.map], ['#/profile', 'Профиль', I.settings]],
  admin: [['#/admin', 'Модели и анализ', I.settings], ['#/queue', 'Очередь и ошибки', I.lessons], ['#/whisper', 'Проверка Whisper', I.chip], ['#/profile', 'Профиль', I.users]],
};
const ROLE = { teacher: ['Кабинет организации', 'Преподаватель'], student: ['Кабинет ученика', 'Ученик'], parent: ['Кабинет родителя', 'Родитель'], admin: ['Системное администрирование', 'Администратор'] };

function shell(active, body) {
  const t = me.role === 'teacher';
  $('#app').innerHTML = `<div class="shell"><aside class="side">
    <div class="logo"><div class="logo-mark">${I.logo}</div>DATERA <span>EDU</span></div>
    <div class="org"><b>${e(me.organization)}</b><small>${ROLE[me.role][0]}</small></div>
    ${t ? `<a class="btn primary wide" href="#/upload">${I.upload} Загрузить запись</a>` : ''}
    <nav class="nav">${NAV[me.role].map((n) => `<a href="${n[0]}" class="${active === n[0] ? 'on' : ''}">${n[2]} ${n[1]}</a>`).join('')}
    ${t ? `<div class="nav-label">Организация</div><a class="off" title="В полной версии">${I.team} Команда</a><a href="#/profile" class="${active === '#/profile' ? 'on' : ''}">${I.settings} Профиль</a>` : ''}</nav>
    <div class="who"><div class="avatar">${e(initials(me.name))}</div><div><b>${e(me.name)}</b><small>${ROLE[me.role][1]}</small></div>
    <button data-act="logout" title="Выйти">${I.logout}</button></div></aside>
    <main class="main"><div class="page">${body}</div></main></div>`;
}

// ---------------------------------------------------------------- login

function loginPage() {
  $('#app').innerHTML = `<div class="login"><div class="card">
    <div class="logo" style="padding:0 0 18px"><div class="logo-mark">${I.logo}</div>DATERA <span>EDU</span></div>
    <h1 style="font-size:20px">Вход в кабинет</h1><div class="sub">Контроль усвоения знаний по записи урока</div>
    <form id="login-form"><label class="f">Электронная почта</label><input class="in" name="email" type="email" autocomplete="username" required>
    <label class="f">Пароль</label><input class="in" name="password" type="password" autocomplete="current-password" required>
    <div class="err" id="login-err"></div><button class="btn primary wide">Войти</button></form>
    <div class="divider">демо-доступ</div>
    <div class="demo-grid"><button class="btn" data-act="demo" data-role="teacher">${I.users} Преподаватель</button>
    <button class="btn" data-act="demo" data-role="student">${I.lessons} Ученик</button>
    <button class="btn" data-act="demo" data-role="parent">${I.team} Родитель</button>
    <button class="btn" data-act="demo" data-role="admin">${I.settings} Администратор</button></div></div></div>`;
  fetch('/api/demo-accounts').then((r) => { if (!r.ok) { $('.divider')?.remove(); $('.demo-grid')?.remove(); } }).catch(() => {});
  $('#login-form').onsubmit = async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    await doLogin(f.get('email'), f.get('password'));
  };
}

async function doLogin(email, password) {
  try {
    me = await api('/login', { json: { email, password } });
    location.hash = { teacher: '#/overview', admin: '#/admin' }[me.role] || '#/home';
    route();
  } catch (err) { $('#login-err').textContent = err.message; }
}

// ---------------------------------------------------------------- player

function playerHtml(L) {
  const marks = L.topics.filter((t) => t.touched && t.first_mention != null)
    .map((t) => `<b class="c-${t.color}" style="left:${(100 * t.first_mention / L.duration).toFixed(2)}%" data-seek="${t.first_mention}" title="${e(t.title)}"></b>`).join('');
  return `<div class="card"><div class="player"><button class="play" data-act="play">${I.play}</button>
    <div class="wave-wrap"><div class="wave" id="wave">${L.peaks.map((p) => `<i style="height:${Math.max(8, Math.round(p * 100))}%"></i>`).join('')}</div>
    <div class="marks">${marks}</div><div class="times"><span id="t-cur">00:00</span><span>${tc(L.duration)}</span></div></div>
    <button class="speed" data-act="speed">1×</button></div></div>`;
}

function mountPlayer(L) {
  if (audio) audio.pause();
  audio = new Audio(`/api/lessons/${L.id}/audio`);
  audio.preload = 'metadata';
  const bars = [...document.querySelectorAll('#wave i')];
  const paint = () => {
    const pos = audio.currentTime / L.duration;
    bars.forEach((b, i) => b.classList.toggle('on', i / bars.length < pos));
    const cur = $('#t-cur'); if (cur) cur.textContent = tc(audio.currentTime);
  };
  audio.ontimeupdate = paint;
  const icon = () => { const b = $('[data-act=play]'); if (b) b.innerHTML = audio.paused ? I.play : I.pause; };
  audio.onplay = icon; audio.onpause = icon; audio.onended = icon;
  $('#wave').onclick = (ev) => { const r = $('#wave').getBoundingClientRect(); seek(((ev.clientX - r.left) / r.width) * L.duration, false); };
}

function seek(t, play = true) {
  if (!audio) return;
  audio.currentTime = Math.max(0, t);
  if (play) audio.play();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

const VERDICT = { correct: ['green', 'Верно'], partial: ['yellow', 'Частично'], wrong: ['red', 'Неверно'], unclear: ['gray', 'Неясно'] };
const verdictPill = (v) => (VERDICT[v] ? pill(VERDICT[v][0], VERDICT[v][1]) : '');
const ul = (items) => `<ul class="list">${items.map((x) => `<li>${e(x)}</li>`).join('')}</ul>`;
let reportView = null;   // 'flow' (questions and answers in order) or 'topics'

function flowHtml(L, forStudent) {
  const byId = Object.fromEntries(L.topics.map((t) => [t.topic_id, t]));
  const who = (sp) => `<span class="tag ${sp}">${sp === 'teacher' ? 'Преподаватель' : forStudent ? 'Ты' : 'Ученик'}</span>`;
  if (!L.two_speakers) {
    return `<div class="banner">${I.info}<span>В записи один голос, поэтому вопросы и ответы не разделены. Ниже речь по порядку.</span></div>
      <div class="card flush">${L.segments.map((s) => { const t = byId[s.topic_slide];
        return `<div class="tr-line">${timeChip(s.start)}<div>${e(s.text)}</div><div>${t ? pill(t.color, t.title) : ''}</div></div>`; }).join('')}</div>`;
  }
  const items = L.pairs.map((p, i) => {
    const a = p.answer;
    const marks = !a ? (p.is_question ? pill('gray', 'Без ответа') : '')
      : verdictPill(p.verdict) + ' ' + (a.topics.length ? a.topics.map((id) => (byId[id] ? `<span class="pill gray">${e(byId[id].title)}</span>` : '')).join(' ') : (p.verdict ? '' : pill('yellow', 'Не совпало с материалом')))
        + (p.pause >= L.pause_seconds ? ` <span class="pill yellow">Пауза ${Math.round(p.pause)} с</span>` : '')
        + (p.note ? `<div class="muted small" style="flex-basis:100%">${e(p.note)}</div>` : '');
    return `<div class="card qa"><div class="qa-row">${timeChip(p.question.start)}<div class="txt">${who('teacher')}<div>${e(p.question.text)}</div></div></div>
      ${a ? `<div class="qa-row ans">${timeChip(a.start)}<div class="txt">${who('student')}<div>${e(a.text)}</div><div class="qa-marks">${marks}</div></div></div>`
          : (marks ? `<div class="qa-row ans"><span></span><div class="qa-marks">${marks}</div></div>` : '')}</div>`;
  }).join('');
  const asked = L.pairs.filter((p) => p.is_question).length, answered = L.pairs.filter((p) => p.answer).length;
  const slow = L.pairs.filter((p) => p.pause >= L.pause_seconds).length;
  return `<div class="muted small">Вопросов преподавателя: ${asked} · ответов ученика: ${answered}${slow ? ` · долгих пауз перед ответом: ${slow}` : ''}</div>${items}`;
}

const timeChip = (t) => `<button class="chip" data-seek="${t}">${I.tri} ${tc(t)}</button>`;

// ---------------------------------------------------------------- teacher pages

async function studentsPage() {
  const list = await api('/students');
  const rows = list.map((s) => {
    const color = s.avg_index == null ? 'gray' : s.avg_index >= 80 ? 'green' : s.avg_index >= 50 ? 'yellow' : 'red';
    return `<tr class="click" data-go="#/students/${s.id}"><td><div class="row"><div class="avatar">${e(initials(s.name))}</div><div><b>${e(s.name)}</b><div class="muted small">${e(s.email)}</div></div></div></td>
      <td>${e(s.subjects.join(', ') || 'нет')}</td>
      <td><div class="row"><span class="num">${s.avg_index == null ? 'нет' : s.avg_index + ' %'}</span>${bar(s.avg_index, color)}</div></td>
      <td>${s.red ? pill('red', s.red + ' ' + plural(s.red, 'тема', 'темы', 'тем')) : '<span class="muted">нет</span>'}</td><td>${fdate(s.last_lesson)}</td></tr>`;
  }).join('');
  shell('#/students', `<div class="head"><div><h1>Ученики</h1><div class="sub">Прогресс каждого ученика по темам материалов</div></div>
    <button class="btn primary" data-act="add-student">${I.plus} Добавить ученика</button></div>
    <div class="card flush">${list.length ? `<table><tr><th>Ученик</th><th>Предмет</th><th>Средний индекс</th><th>Красные темы</th><th>Последний урок</th></tr>${rows}</table>` : '<div class="empty">Пока нет учеников</div>'}</div>`);
}

async function addStudentDialog() {
  const subjects = await api('/subjects');
  modal(`<h2>Новый ученик</h2><form id="st-form"><label class="f">Имя и фамилия</label><input class="in" name="name" required>
    <label class="f">Электронная почта</label><input class="in" name="email" type="email" required>
    <label class="f">Пароль для входа</label><input class="in" name="password" type="text" minlength="6" required>
    <label class="f">Предмет</label><select class="in" name="subject_id">${subjects.map((s) => `<option value="${s.id}">${e(s.name)}</option>`).join('')}</select>
    <div class="err" id="st-err"></div><div class="actions"><button type="button" class="btn" data-act="close">Отмена</button><button class="btn primary">Добавить</button></div></form>`);
  $('#st-form').onsubmit = async (ev) => {
    ev.preventDefault();
    try { await api('/students', { json: Object.fromEntries(new FormData(ev.target)) }); closeModal(); toast('Ученик добавлен'); route(); }
    catch (err) { $('#st-err').textContent = err.message; }
  };
}

const changeText = (c) => (c == null ? '<span class="muted">первый разбор</span>' : c === 0 ? '<span class="muted">без изменений</span>'
  : `<span class="${c > 0 ? 't-green' : 't-red'}">${c > 0 ? '↑ +' : '↓ '}${c} %</span>`);

function lessonStatus(l) {
  if (l.status === 'done') return pill('green', 'Готов');
  if (l.status === 'error') return `<span class="pill red" title="${e(l.error)}"><i class="dot c-red"></i>Ошибка</span>`;
  return `<span class="pill blue"><span class="spin" style="width:10px;height:10px"></span>${e(l.stage || 'В очереди')}</span>`;
}

function lessonsTable(list, withStudent) {
  if (!list.length) return '<div class="empty">Уроков пока нет. Загрузите первую запись.</div>';
  return `<table><tr><th>Урок</th>${withStudent ? '<th>Ученик</th>' : ''}<th>Дата</th><th>Длительность</th><th>Статус</th><th>Индекс</th><th></th></tr>${list.map((l) => {
    const color = l.index == null ? 'gray' : l.index >= 80 ? 'green' : l.index >= 50 ? 'yellow' : 'red';
    return `<tr class="${l.status === 'done' ? 'click' : ''}" ${l.status === 'done' ? `data-go="#/lessons/${l.id}"` : ''}><td><b>${e(l.title)}</b><div class="muted small">${e(l.subject_name)}</div></td>
      ${withStudent ? `<td>${e(l.student_name)}</td>` : ''}<td>${fdate(l.date)}</td><td>${mins(l.duration) || '<span class="muted">нет</span>'}</td><td>${lessonStatus(l)}</td>
      <td>${l.index == null ? '' : `<span class="num t-${color}">${l.index} %</span>`}</td>
      <td style="text-align:right">${l.status === 'done' ? `<a href="#/lessons/${l.id}">Отчёт</a>` : l.status === 'error' ? `<button class="link-btn" data-act="retry" data-id="${l.id}">Повторить</button>` : ''}</td></tr>`;
  }).join('')}</table>`;
}

const pollIfBusy = (list) => { if (list.some((l) => l.status === 'queued' || l.status === 'processing')) pollTimer = setTimeout(route, 2500); };

async function lessonsPage() {
  const list = await api('/lessons');
  shell('#/lessons', `<div class="head"><div><h1>Уроки</h1><div class="sub">Записи и статус их обработки</div></div>
    <a class="btn primary" href="#/upload">${I.upload} Загрузить запись</a></div><div class="card flush">${lessonsTable(list, true)}</div>`);
  pollIfBusy(list);
}

async function studentCardPage(id) {
  const [s, allParents] = await Promise.all([api('/students/' + id), api('/parents')]);
  const topics = s.maps.flatMap((m) => m.topics).filter((t) => t.index != null);
  const avg = topics.length ? Math.round(topics.reduce((a, t) => a + t.index, 0) / topics.length) : null;
  const weak = topics.filter((t) => t.color !== 'green');
  mapSel = {};
  const mapsHtml = () => s.maps.map((m, si) => {
    const ls = lessonsOf(s.lessons, m.subject), sel = mapSelOf(si), all = asOf(m, ls, sel);
    const rows = sel.status === 'all' ? all : all.filter((t) => t.color === sel.status);
    return `<div class="card flush"><div style="padding:16px 20px 14px"><div class="card-title" style="margin:0">Карта знаний: ${e(m.subject)}</div>
    <div class="muted small" style="margin-bottom:12px">Индекс считается по последнему уроку, где тема обсуждалась. Красный ниже 50 %, жёлтый 50–79 %, зелёный от 80 %. Выберите урок, чтобы увидеть карту на его конец.</div>${mapFilter(si, ls, sel, all, TL)}</div>
    ${rows.length ? `<table><tr><th>Тема</th><th>Статус</th><th>Индекс</th><th>Изменение</th><th>Последний разбор</th></tr>${rows.map((t) => `<tr class="${t.here ? 'hl' : ''}"><td><b>${e(t.title)}</b>${t.here ? ' <span class="pill blue">на уроке</span>' : ''}</td>
      <td>${pill(t.color, t.teacher_label)}</td><td><div class="row"><span class="num" style="width:48px">${t.index == null ? '' : t.index + ' %'}</span>${bar(t.index, t.color)}</div></td>
      <td>${t.index == null ? '' : changeText(t.change)}</td><td>${t.last_lesson_id ? `<a href="#/lessons/${t.last_lesson_id}">${fdate(t.last_date)}</a>` : '<span class="muted">нет</span>'}</td></tr>`).join('')}</table>` : '<div class="empty">Тем с таким статусом нет</div>'}</div>`; }).join('');
  const draw = () => shell('#/students', `${crumbs([['Ученики', '#/students'], [s.name]])}
    <div class="head"><div><h1>${e(s.name)}</h1><div class="sub">${e(s.email)}</div></div><a class="btn primary" href="#/upload?student=${s.id}">${I.upload} Загрузить запись</a></div>
    <div class="stats"><div class="card stat"><small>Средний индекс</small><div>${avg == null ? 'нет данных' : avg + ' %'}</div></div>
      <div class="card stat"><small>Требуют внимания</small><div>${weak.length} ${plural(weak.length, 'тема', 'темы', 'тем')}</div></div>
      <div class="card stat"><small>Последний урок</small><div>${s.lessons.length ? fdate(s.lessons[0].date) : 'нет'}</div></div></div>
    <div class="stack">${s.stuck.length ? `<div class="banner warn">${I.info}<span><b>Застрял на темах:</b> ${s.stuck.map((t) => e(t.title)).join(', ')}. Тема остаётся красной уже ${s.stuck[0].times} ${plural(s.stuck[0].times, 'урок', 'урока', 'уроков')} подряд. Стоит разобрать её иначе.</span></div>` : ''}
    <div class="grid2"><div class="card"><div class="card-title">Динамика индекса по урокам</div>${trendChart(s.trend)}</div>${parentsCard(s, allParents)}</div>
    ${mapsHtml() || '<div class="card empty">Ученик пока не записан на предмет</div>'}
    <div class="card flush"><div class="card-title" style="padding:16px 20px 0">Уроки</div>${lessonsTable(s.lessons, false)}</div></div>`);
  mapRedraw = draw; draw();
  pollIfBusy(s.lessons);
}

async function uploadPage(query) {
  const [students, subjects] = await Promise.all([api('/students'), api('/subjects')]);
  const pre = new URLSearchParams(query).get('student');
  shell('', `${crumbs([['Уроки', '#/lessons'], ['Загрузка записи']])}<div class="head"><div><h1>Загрузка записи</h1>
    <div class="sub">Аудио или видео урока. Система распознает речь и сверит её с темами предмета.</div></div></div>
    <div class="card" style="max-width:640px"><form id="up-form">
    <label class="f" style="margin-top:0">Ученик</label><select class="in" name="student_id" required>${students.map((s) => `<option value="${s.id}" ${String(s.id) === pre ? 'selected' : ''}>${e(s.name)}</option>`).join('')}</select>
    <label class="f">Предмет</label><select class="in" name="subject_id" required>${subjects.map((s) => `<option value="${s.id}">${e(s.name)} (тем: ${s.topics.length})</option>`).join('')}</select>
    <div class="muted small" style="margin-top:6px">Темы берутся из материалов предмета. Новую презентацию можно добавить в разделе <a href="#/subjects">«Предметы и материалы»</a>.</div>
    <div class="row" style="align-items:flex-start"><div style="flex:2"><label class="f">Название урока</label><input class="in" name="title" placeholder="Например, Урок 5. Обучение сети"></div>
    <div style="flex:1"><label class="f">Дата</label><input class="in" type="date" name="date" value="${new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)}"></div></div>
    <label class="f">Запись</label><label class="drop" id="drop"><input type="file" name="file" accept="audio/*,video/*,.mkv,.m4a" required>
      <div id="drop-text">${I.upload}<div style="margin-top:6px"><b>Выберите файл</b> с записью урока</div><div class="small">MP3, WAV, M4A, MP4, MOV, WEBM, до 2 ГБ</div></div></label>
    <div class="err" id="up-err"></div><button class="btn primary wide" id="up-btn">Загрузить и проанализировать</button></form></div>`);
  $('#drop input').onchange = (ev) => { const f = ev.target.files[0]; if (f) { $('#drop').classList.add('has'); $('#drop-text').innerHTML = `<b>${e(f.name)}</b><div class="small">${(f.size / 1048576).toFixed(1)} МБ</div>`; } };
  $('#up-form').onsubmit = async (ev) => {
    ev.preventDefault();
    $('#up-btn').disabled = true; $('#up-btn').innerHTML = '<span class="spin"></span> Загрузка...';
    try { await api('/lessons', { method: 'POST', body: new FormData(ev.target) }); toast('Запись загружена, идёт обработка'); location.hash = '#/lessons'; }
    catch (err) { $('#up-err').textContent = err.message; $('#up-btn').disabled = false; $('#up-btn').textContent = 'Загрузить и проанализировать'; }
  };
}

async function subjectsPage() {
  const list = await api('/subjects');
  const cards = list.map((s) => `<div class="card"><div class="spread"><div><h2 style="font-size:17px">${e(s.name)}</h2>
      <div class="muted small">Учеников: ${s.students.length} · материалов: ${s.materials.length} · тем: ${s.topics.length}</div></div>
      <label class="btn">${I.upload} Загрузить материал<input type="file" hidden accept=".pptx,.pdf,.txt,.md" data-material="${s.id}"></label></div>
    ${s.materials.length ? `<div class="row" style="flex-wrap:wrap;margin-top:12px">${s.materials.map((m) => `<span class="chip plain">${I.doc} ${e(m.filename)}</span>`).join('')}</div>` : ''}
    ${s.topics.length ? `<table style="margin-top:14px"><tr><th style="width:70px">Слайд</th><th>Тема</th><th>Ключевые пункты</th><th style="width:40px"></th></tr>${s.topics.map((t) => `<tr><td class="muted">${t.slide}</td><td><b>${e(t.title)}</b></td>
      <td class="muted small">${t.points.map(e).join('<br>')}</td><td><button class="icon-btn" title="Удалить тему" data-act="del-topic" data-id="${t.id}">${I.x}</button></td></tr>`).join('')}</table>`
    : '<div class="empty">Загрузите презентацию или PDF: система разобьёт материал на темы</div>'}</div>`).join('');
  shell('#/subjects', `<div class="head"><div><h1>Предметы и материалы</h1><div class="sub">Темы предмета берутся из материалов: один слайд считается одной темой</div></div>
    <button class="btn primary" data-act="add-subject">${I.plus} Добавить предмет</button></div><div class="stack">${cards || '<div class="card empty">Предметов пока нет</div>'}</div>`);
  document.querySelectorAll('[data-material]').forEach((inp) => {
    inp.onchange = async () => {
      const fd = new FormData(); fd.append('file', inp.files[0]);
      try { await api(`/subjects/${inp.dataset.material}/materials`, { method: 'POST', body: fd }); toast('Материал загружен, темы выделены'); route(); }
      catch (err) { modal(`<h2>Не удалось загрузить</h2><p>${e(err.message)}</p><div class="actions"><button class="btn primary" data-act="close">Понятно</button></div>`); }
    };
  });
}

function processingBody(L) {
  return L.status === 'error'
    ? `<div class="card"><div class="card-title t-red">Ошибка обработки</div><p>${e(L.error)}</p>${me.role === 'teacher' ? `<button class="btn primary" data-act="retry" data-id="${L.id}">Запустить заново</button>` : ''}</div>`
    : `<div class="card"><div class="row"><span class="spin"></span><b>Урок обрабатывается</b></div><p class="muted">${e(L.stage || 'В очереди')}</p><p class="muted small">Страница обновится сама, когда отчёт будет готов.</p></div>`;
}

function topicCard(t) {
  const ev = t.evidence.map((x) => `<div class="ev">${x.question ? `<div class="qa-row">${timeChip(x.question.start)}<div class="txt"><span class="tag teacher">Вопрос</span><div>${e(x.question.text)}</div></div></div>` : ''}
    <div class="qa-row ${x.question ? 'ans' : ''}">${timeChip(x.answer.start)}<div class="txt"><span class="tag student">Ответ</span><div>${e(x.answer.text)}</div>
    ${x.verdict || x.note ? `<div class="qa-marks">${verdictPill(x.verdict)}${x.note ? `<span class="muted small">${e(x.note)}</span>` : ''}</div>` : ''}</div></div></div>`).join('');
  const pts = t.points.map((p) => `<li><span class="${p.covered ? 'mark-ok' : 'mark-no'}">${p.covered ? I.check : I.x}</span>
    <div class="txt">${e(p.text)}${!t.evidence.length && p.covered && p.quote ? `<div class="quote">«${e(p.quote)}»</div>` : ''}</div>
    ${!t.evidence.length && p.covered && p.start != null ? timeChip(p.start) : ''}</li>`).join('');
  const done = t.points.filter((p) => p.covered).length;
  const foot = t.confirmed
    ? `<span class="confirmed">${I.check} ${t.changed ? 'Статус изменён вами' : 'Подтверждено вами'}</span>`
    : `<span class="row"><button class="btn sm" data-act="change" data-id="${t.assessment_id}">${I.edit} Изменить</button><button class="btn sm primary" data-act="confirm" data-id="${t.assessment_id}">${I.check} Подтвердить</button></span>`;
  return `<div class="card topic ${t.color}"><div class="topic-head"><i class="dot c-${t.color}"></i><h2>${e(t.title)}</h2>${pill(t.color, t.teacher_label)}${t.touched ? `<span class="num t-${t.color}">${t.index} %</span>` : ''}</div>
    ${t.analysis ? `<p class="analysis">${e(t.analysis)}</p>` : ''}${ev ? `<div class="evs">${ev}</div>` : ''}
    <details class="pts" ${t.evidence.length ? '' : 'open'}><summary>Пункты темы из материала: прозвучало ${done} из ${t.points.length} · слайд ${t.slide}</summary><ul class="points">${pts}</ul></details>
    ${t.changed && t.comment ? `<div class="muted small" style="margin-top:10px">Ваш комментарий: ${e(t.comment)}</div>` : ''}
    <div class="topic-foot"><span>${t.touched ? `Ответы по теме: ${tc(t.seconds)}${t.changed ? ` · оценка системы: ${t.auto_index} %` : ''}` : 'Тема на уроке не обсуждалась'}</span>
    ${t.touched || t.confirmed ? foot : `<button class="btn sm" data-act="change" data-id="${t.assessment_id}">${I.edit} Оценить вручную</button>`}</div></div>`;
}

const idxColor = (i) => (i == null ? 'gray' : i >= 80 ? 'green' : i >= 50 ? 'yellow' : 'red');

function tiles(L, labels) {
  return `<div class="tiles"><div class="card tile main"><small>Индекс урока</small><div class="t-${idxColor(L.index)}">${L.index ?? 0} %</div>${bar(L.index, idxColor(L.index))}</div>
    ${[['green', labels[0]], ['yellow', labels[1]], ['red', labels[2]]].map(([c, l]) => `<div class="card tile"><small><i class="dot c-${c}"></i> ${l}</small><div>${L.counts[c]}</div><span class="muted small">${plural(L.counts[c], 'тема', 'темы', 'тем')}</span></div>`).join('')}</div>`;
}

function engineNote(L) {
  const badge = L.engine === 'llm' ? `<span class="pill blue">${I.chip} Анализ: языковая модель ${e(L.llm.model)}</span>` : `<span class="pill gray">${I.chip} Анализ: эмбеддинги, без языковой модели</span>`;
  const err = L.llm_error ? `<div class="banner warn">${I.info}<span><b>Языковая модель не ответила.</b> ${e(L.llm_error)} Показан анализ по эмбеддингам; после исправления настроек нажмите «Пересчитать анализ».</span></div>` : '';
  return { badge, err };
}

let currentLesson = null;

async function lessonTeacherPage(id) {
  const L = currentLesson = await api('/lessons/' + id);
  const back = me.role === 'admin' ? ['Очередь и ошибки', '#/queue'] : ['Уроки', '#/lessons'];
  const active = me.role === 'admin' ? '#/queue' : '#/lessons';
  const head = `${crumbs([back, [L.student_name, me.role === 'admin' ? '' : '#/students/' + L.student_id], [fdate(L.date)]])}
    <div class="head"><div><h1>${e(L.title)} · ${fdate(L.date)}</h1><div class="sub">${e(L.student_name)} · ${e(L.subject_name)}${L.duration ? ' · ' + mins(L.duration) : ''}</div></div>
    ${L.status === 'done' ? `<span class="row" style="flex-wrap:wrap"><button class="btn" data-act="reanalyse" data-id="${id}" title="Повторить анализ с текущими настройками">Пересчитать анализ</button><a class="btn" href="#/lessons/${id}/model">${I.chip} Как работает модель</a><a class="btn" href="#/lessons/${id}/transcript">${I.doc} Транскрипт</a></span>` : ''}</div>`;
  if (L.status !== 'done') { shell(active, head + processingBody(L)); if (L.status !== 'error') pollTimer = setTimeout(route, 2500); return; }
  const touched = L.topics.filter((t) => t.touched), rest = L.topics.filter((t) => !t.touched);
  const view = reportView || (L.two_speakers ? 'flow' : 'topics');
  const note = engineNote(L);
  const tabs = [['flow', 'По ходу урока'], ['topics', 'По темам'], ['roles', 'Отчёты для ролей']].map(([v, l]) => `<button class="${view === v ? 'on' : ''}" data-act="view" data-view="${v}">${l}</button>`).join('');
  const outside = L.outside.length ? `<div class="card warn"><div class="spread"><div class="card-title" style="margin:0">Вне материала</div><span class="pill yellow">Не входит в индекс</span></div>
    <div class="stack" style="gap:10px;margin-top:10px">${L.outside.map((o) => `<div><div class="row">${timeChip(o.start)}<span class="muted small">${o.note ? e(o.note) : tc(o.end - o.start)}</span></div><div class="small" style="margin-top:4px">${e(o.text)}</div></div>`).join('')}</div>
    <div class="muted small" style="margin-top:10px">Этого нет в материалах предмета. Если тема нужна, добавьте её в материал.</div></div>` : '';
  const roles = `<div class="card role-card"><div class="card-title"><span class="tag teacher">Преподавателю</span></div><p>${e(L.summary)}</p>
      ${L.strengths.length ? `<h3>Что получилось</h3>${ul(L.strengths)}` : ''}${L.difficulties.length ? `<h3>Сложности</h3>${ul(L.difficulties)}` : ''}${L.recommendations.length ? `<h3>На следующий урок</h3>${ul(L.recommendations)}` : ''}</div>
    <div class="card role-card"><div class="card-title"><span class="tag student">Ученику</span></div><p>${e(L.student.summary)}</p>
      ${L.student.good.length ? `<h3>Что получилось</h3>${ul(L.student.good)}` : ''}${L.student.repeat.length ? `<h3>Что повторить</h3>${ul(L.student.repeat.map((r) => r.what + (r.tip ? '. ' + r.tip : '')))}` : ''}</div>
    <div class="card role-card"><div class="card-title"><span class="tag parent">Родителю</span></div><p>${e(L.parent_text)}</p></div>
    ${L.engine === 'llm' ? '' : `<div class="muted small">Сейчас тексты собраны по шаблону. Чтобы их писала языковая модель, администратор включает её в разделе «Модели и анализ».</div>`}`;
  const main = view === 'flow' ? flowHtml(L, false) : view === 'roles' ? roles
    : `<div class="banner">${I.info}<span>Оценка системы — подсказка. Подтвердите или измените статус: последнее слово за вами.</span><span class="end">Проверено ${L.checked} из ${L.to_check}</span></div>
      ${touched.map(topicCard).join('')}${rest.length ? `<div class="muted small" style="margin:6px 2px 0">Не обсуждались на уроке</div>${rest.map(topicCard).join('')}` : ''}`;
  shell(active, `${head}<div class="stack">${note.err}${playerHtml(L)}${tiles(L, ['Закреплено', 'Требует закрепления', 'Не усвоено'])}
    <div class="grid2"><div class="stack"><div class="spread" style="flex-wrap:wrap"><div class="switch">${tabs}</div>${note.badge}</div>${main}</div>
    <div class="stack">
      <div class="card"><div class="card-title">Итог урока</div><div class="small">${e(L.summary)}</div>
        <div class="muted small" style="margin-top:10px">Обсуждали ${touched.length} из ${L.topics.length} ${plural(L.topics.length, 'темы', 'тем', 'тем')}${L.on_topic_share != null ? ` · ${L.on_topic_share} % речи ученика по материалу` : ''}</div></div>
      ${L.strengths.length ? `<div class="card side-list ok"><div class="card-title"><span class="mark-ok">${I.check}</span>Что получилось</div>${ul(L.strengths)}</div>` : ''}
      ${L.difficulties.length ? `<div class="card side-list bad"><div class="card-title"><span class="t-red">${I.info}</span>Сложности</div>${ul(L.difficulties)}</div>` : ''}
      <div class="card side-list"><div class="card-title">На следующий урок</div>${L.recommendations.length ? ul(L.recommendations) : '<div class="muted small">Все затронутые темы раскрыты полностью.</div>'}
        ${L.untouched.length ? `<div class="muted small" style="margin-top:8px">Не обсуждались: ${L.untouched.map(e).join(', ')}</div>` : ''}</div>
      ${outside}
    </div></div></div>`);
  mountPlayer(L);
}

function changeDialog(id) {
  const t = currentLesson.topics.find((x) => x.assessment_id === +id);
  const cur = t.touched ? (t.index >= 80 ? 100 : t.index >= 50 ? 50 : 0) : 50;
  const opt = (v, title, hint, color) => `<label class="opt"><input type="radio" name="level" value="${v}" ${cur === v ? 'checked' : ''}><div><b>${title}</b><small>${hint}</small></div><i class="dot c-${color}"></i></label>`;
  modal(`<h2>Изменить статус темы</h2><div class="muted small" style="margin:4px 0 14px">${e(t.title)} · ${e(currentLesson.title)}</div>
    <div class="spread card" style="padding:10px 12px;margin-bottom:14px"><span class="muted small">Оценка системы</span>${t.touched ? pill(t.auto_index >= 80 ? 'green' : t.auto_index >= 50 ? 'yellow' : 'red', t.auto_index + ' %') : pill('gray', 'нет')}</div>
    <form id="ch-form"><div class="small" style="font-weight:500;margin-bottom:8px">Ваша оценка</div>
    ${opt(0, 'Не усвоено', 'Тема не раскрыта или раскрыта с ошибками', 'red')}${opt(50, 'Усвоено частично', 'Есть пробелы, нужно закрепить', 'yellow')}${opt(100, 'Усвоено', 'Тема раскрыта полностью', 'green')}
    <label class="f">Комментарий (по желанию)</label><textarea class="in" name="comment" placeholder="Например: путает термины, нужна практика">${e(t.comment)}</textarea>
    <div class="muted small" style="margin-top:8px">Индекс и карта знаний пересчитаются, изменение сохранится в истории.</div>
    <div class="actions"><button type="button" class="btn" data-act="close">Отмена</button><button class="btn primary">Сохранить</button></div></form>`);
  $('#ch-form').onsubmit = async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    await api('/assessments/' + id, { json: { action: 'change', level: +f.get('level'), comment: f.get('comment') } });
    closeModal(); toast('Статус изменён, карта знаний пересчитана'); route();
  };
}

async function transcriptPage(id) {
  const L = currentLesson = await api('/lessons/' + id);
  const byId = Object.fromEntries(L.topics.map((t) => [t.topic_id, t]));
  const name = { teacher: 'Преподаватель', student: 'Ученик' };
  const total = (sp) => L.turns.filter((t) => t.speaker === sp).reduce((a, t) => a + t.end - t.start, 0);
  const speakers = L.two_speakers
    ? `<div class="card"><div class="spread"><div><div class="card-title" style="margin-bottom:6px">Говорящие</div>
        <span class="row" style="flex-wrap:wrap"><span class="tag teacher">Преподаватель · ${tc(total('teacher'))}</span><span class="tag student">Ученик · ${tc(total('student'))}</span>
        <span class="muted small">Определено автоматически по голосу. Если роли перепутаны, поменяйте их.</span></span></div>
        <button class="btn" data-act="swap" data-id="${id}">Поменять роли местами</button></div></div>`
    : `<div class="banner">${I.info}<span>В записи найден один голос, роли не разделены.</span></div>`;
  shell('#/lessons', `${crumbs([['Уроки', '#/lessons'], [L.title, '#/lessons/' + id], ['Транскрипт']])}
    <div class="head"><div><h1>Транскрипт урока</h1><div class="sub">${e(L.student_name)} · ${fdate(L.date)} · язык речи: ${e(L.language)} · реплик: ${L.turns.length}</div></div><a class="btn" href="#/lessons/${id}">К отчёту</a></div>
    <div class="stack">${playerHtml(L)}${speakers}<div class="card flush">${L.turns.map((t) => `<div class="tr-line turn ${t.speaker || ''}">${timeChip(t.start)}
      <div>${t.speaker ? `<span class="tag ${t.speaker}">${name[t.speaker]}</span>` : ''}<div>${e(t.text)}</div></div>
      <div>${t.topics.map((tid) => (byId[tid] ? pill(byId[tid].color, byId[tid].title) : '')).join(' ')}</div></div>`).join('')}</div></div>`);
  mountPlayer(L);
}

async function modelPage(id) {
  const L = await api('/lessons/' + id);
  const w = L.model.whisper, tm = L.model.timings;
  const conf = L.segments.map((s) => s.confidence);
  const avg = conf.reduce((a, b) => a + b, 0) / conf.length;
  const step = (n, title, body) => `<div class="card"><div class="card-title"><span class="avatar" style="width:26px;height:26px">${n}</span>${title}</div>${body}</div>`;
  shell('#/lessons', `${crumbs([['Уроки', '#/lessons'], [L.title, '#/lessons/' + id], ['Как работает модель']])}
    <div class="head"><div><h1>Как работает модель</h1><div class="sub">Путь записи «${e(L.title)}» через нейросети по шагам</div></div><a class="btn" href="#/lessons/${id}">К отчёту</a></div>
    <div class="stats"><div class="card stat"><small>OpenAI Whisper ${e(w.name)}</small><div>${(w.parameters / 1e6).toFixed(0)} млн параметров</div></div>
      <div class="card stat"><small>Распознавание ${mins(L.duration)} записи</small><div>${tm.asr} с</div></div>
      <div class="card stat"><small>Средняя уверенность декодера</small><div>${(avg * 100).toFixed(0)} %</div></div></div>
    <div class="stack">
    ${step(1, 'Вход сети: лог-мел-спектрограмма', `<p class="small muted" style="margin-top:0">ffmpeg приводит запись к моно 16 кГц, затем звук превращается в картинку «время × частота». Ниже первые 30 секунд: именно это видит энкодер Whisper.</p><img class="mel" src="/api/lessons/${id}/mel.png" alt="Спектрограмма">`)}
    ${step(2, 'Определение языка', `<p class="small muted" style="margin-top:0">Декодер по спектрограмме предсказывает вероятность каждого языка.</p><div class="bars">${L.model.language_probs.map(([l, p]) => `<div><b>${e(l)}</b>${bar(p * 100, 'green')}<span class="num">${(p * 100).toFixed(1)} %</span></div>`).join('')}</div>`)}
    ${step(3, 'Генерация текста', `<p class="small muted" style="margin-top:0">Transformer: энкодер ${w.encoder_layers} слоёв, декодер ${w.decoder_layers} слоёв, скрытый слой ${w.hidden_size}, ${w.attention_heads} голов внимания, словарь ${w.vocab_size} токенов, устройство ${e(w.device)}. Декодер выдаёт токены по одному; уверенность фразы — exp от средней лог-вероятности её токенов.</p>
      <div class="wave" style="height:60px;cursor:default">${conf.map((c) => `<i class="on" style="height:${Math.round(c * 100)}%" title="${(c * 100).toFixed(0)} %"></i>`).join('')}</div><div class="times"><span>первая фраза</span><span>последняя фраза</span></div>`)}
    ${step(4, 'Разделение говорящих', `<p class="small muted" style="margin:0">Третья нейросеть, <b>${e(L.speakers.model || 'microsoft/wavlm-base-plus-sv')}</b>, превращает каждый отрезок речи в «отпечаток голоса». Отпечатки делятся на две группы; если группы почти совпадают, в записи один голос. ${L.speakers.voice_similarity != null ? `В этой записи сходство групп ${L.speakers.voice_similarity}, найдено голосов: ${L.speakers.speakers}.` : ''} Преподавателем считается тот, кто задаёт больше вопросов. В диалоге оцениваются только ответы ученика.</p>`)}
    ${step(5, 'Сопоставление с темами', `<p class="small muted" style="margin:0">Вторая нейросеть, <b>${e(L.model.embedding_model)}</b>, превращает каждый пункт слайда и каждую фразу в вектор. Если косинусное сходство не ниже ${L.model.threshold}, пункт считается прозвучавшим. Индекс темы — доля прозвучавших пунктов; цвет и статус считает обычный код, а не нейросеть.</p>`)}
    ${step(6, 'Проверка ответов языковой моделью', `<p class="small muted" style="margin:0">${L.engine === 'llm' ? `Этот урок разобрала модель <b>${e(L.llm.model)}</b> (промпт ${e(L.llm.prompt_version)}).` : 'Для этого урока языковая модель не использовалась.'} Модель получает реплики с номерами и темы материала и возвращает JSON: по каждой теме номер вопроса, номер ответа и вердикт. Тайм-коды и цитаты подставляет сервер из расшифровки; ссылка на несуществующую реплику, на реплику преподавателя вместо ответа или на вопрос позже ответа отбрасывается. Индекс и цвет по-прежнему считает код.</p>`)}
    <div class="muted small">Время по этапам, с: подготовка аудио ${tm.audio}, загрузка Whisper ${tm.load_whisper}, распознавание ${tm.asr}, разделение говорящих ${tm.diarization ?? 'нет'}, загрузка эмбеддингов ${tm.load_embedder}, анализ ${tm.analysis}</div></div>`);
}

// ---------------------------------------------------------------- student pages

let childId = 0;   // the child a parent is looking at

async function homePage() {
  const parent = me.role === 'parent';
  const d = await api('/my/home' + (parent && childId ? '?child=' + childId : ''));
  if (parent && !d.child) return shell('#/home', '<div class="card empty">К вашему аккаунту пока не привязан ученик.</div>');
  const topics = d.maps.flatMap((m) => m.topics).filter((t) => t.index != null);
  const n = (c) => topics.filter((t) => t.color === c).length;
  const repeat = topics.filter((t) => t.color !== 'green').sort((a, b) => a.index - b.index).slice(0, 3);
  const cards = d.lessons.map((l) => (l.status === 'done'
    ? `<a class="card lesson-card" href="#/lessons/${l.id}"><div class="muted small">${fdate(l.date)} · ${mins(l.duration)}</div><b style="font-size:15px">${e(l.title)}</b><div class="muted small">${e(l.subject_name)}</div>
       <div class="foot">${l.repeat ? `<span class="pill yellow">${l.repeat} повторить</span>` : ''}${l.ok ? `<span class="pill green">${l.ok} получилось</span>` : ''}</div></a>`
    : `<div class="card lesson-card" style="background:#fafbfc"><div class="muted small">${fdate(l.date)}</div><b style="font-size:15px">${l.status === 'error' ? 'Не удалось обработать урок' : 'Урок обрабатывается'}</b>
       <div class="muted small">Отчёт появится, как только система разберёт запись.</div><div class="foot muted small row">${l.status === 'error' ? '' : '<span class="spin"></span>'} ${e(l.status === 'error' ? 'Преподаватель уже в курсе' : l.stage || 'В очереди')}</div></div>`)).join('');
  const kids = parent && d.children.length > 1 ? `<div class="switch">${d.children.map((c) => `<button class="${c.id === d.child.id ? 'on' : ''}" data-act="child" data-id="${c.id}">${e(c.name)}</button>`).join('')}</div>` : '';
  shell('#/home', `<div class="head"><div><h1>${parent ? e(d.child.name) : `Привет, ${e(me.name.split(' ')[0])}!`}</h1><div class="sub">${d.maps.map((m) => `${e(m.subject)} · преподаватель ${e(m.teacher)}`).join(' · ') || 'Пока нет предметов'}</div></div>${kids}</div>
    <div class="grid2" style="margin-bottom:24px"><div class="card"><div class="spread"><div class="card-title" style="margin:0">${parent ? 'Над чем стоит поработать' : 'Что повторить'}</div><a href="#/map" class="small">Вся карта знаний</a></div>
      <div class="stack" style="margin-top:14px">${repeat.length ? repeat.map((t) => `<div class="repeat ${t.color}"><b>${e(t.title)}</b> <span class="small t-${t.color}">${e(t.student_label)}</span>
        <div class="muted small">${t.missing.length ? (parent ? 'Не прозвучало: ' : 'Повтори: ') + e(t.missing[0]) : 'Стоит закрепить тему ещё раз'}</div></div>`).join('') : `<div class="muted">${topics.length ? 'Повторять пока нечего. Отличная работа!' : 'Здесь появятся темы после первого урока.'}</div>`}</div></div>
    <div class="card"><div class="muted small">Темы по предмету</div><div style="font-size:22px;font-weight:700;margin-top:4px">${n('green')} из ${topics.length} <span class="small t-green" style="font-weight:500">получается</span></div>
      <div class="seg">${['red', 'yellow', 'green'].map((c) => (n(c) ? `<i class="c-${c}" style="flex:${n(c)}"></i>` : '')).join('') || '<i class="c-gray" style="flex:1"></i>'}</div>
      ${[['green', 'Получается'], ['yellow', 'Почти получилось'], ['red', 'Нужно повторить']].map(([c, l]) => `<div class="spread small" style="margin-top:6px"><span class="row"><i class="dot c-${c}"></i>${l}</span><b>${n(c)}</b></div>`).join('')}</div></div>
    ${progressCard(d, parent)}<h2 style="font-size:17px;margin-bottom:12px">${parent ? 'Уроки' : 'Мои уроки'}</h2>${cards ? `<div class="lesson-grid">${cards}</div>` : '<div class="card empty">Уроков пока нет</div>'}`);
  pollIfBusy(d.lessons);
}

const topicsSide = (L) => { const touched = L.topics.filter((t) => t.touched);
  return `<div class="card"><div class="card-title">Темы урока</div>${touched.length ? touched.map((t) => `<div class="spread" style="padding:8px 0;border-bottom:1px solid #eef0f3"><div><b class="small">${e(t.title)}</b><div class="small t-${t.color}">${e(t.student_label)}</div></div><span class="num small t-${t.color}">${t.index} %</span></div>`).join('') : '<div class="muted small">Темы материала на уроке не обсуждались.</div>'}</div>`; };

async function lessonStudentPage(id) {
  const L = currentLesson = await api('/lessons/' + id);
  const parent = me.role === 'parent';
  const head = `${crumbs([[parent ? 'Уроки ребёнка' : 'Мои уроки', '#/home'], [fdate(L.date)]])}<div class="head"><div><h1>${e(L.title)} · ${fdate(L.date)}</h1><div class="sub">${parent ? e(L.student_name) + ' · ' : ''}${e(L.subject_name)}${L.duration ? ' · ' + mins(L.duration) : ''}</div></div></div>`;
  if (L.status !== 'done') { shell('#/home', head + processingBody(L)); if (L.status !== 'error') pollTimer = setTimeout(route, 2500); return; }
  const byId = Object.fromEntries(L.topics.map((t) => [t.topic_id, t]));
  const repeat = L.student.repeat.filter((r) => byId[r.topic_id]);
  const repeatHtml = repeat.length ? `<div class="stack">${repeat.map((r) => { const t = byId[r.topic_id];
    return `<div class="repeat ${t.color}"><div class="spread"><b>${e(t.title)}</b>${!parent && t.first_mention != null ? timeChip(t.first_mention) : ''}</div>
      <div class="small" style="margin-top:2px">${e(r.what)}</div>${r.tip ? `<div class="muted small" style="margin-top:2px">${e(r.tip)}</div>` : ''}</div>`; }).join('')}</div>`
    : `<div class="muted">${parent ? 'Всё, что обсуждали на уроке, получилось.' : 'Всё, что обсуждали, получилось. Так держать!'}</div>`;
  const body = parent
    ? `<div class="card soft"><div class="card-title">Коротко об уроке</div><div style="font-size:15px">${e(L.parent_text)}</div></div>
       <div class="card"><div class="card-title"><span class="t-yellow">${I.info}</span>Как помочь дома</div>${repeatHtml}</div>
       ${L.student.good.length ? `<div class="card"><div class="card-title"><span class="mark-ok">${I.check}</span>Что получилось</div>${ul(L.student.good)}</div>` : ''}`
    : `<div class="card soft"><div class="card-title">Коротко об уроке</div><div style="font-size:15px">${e(L.student.summary)}</div></div>
       <div class="card"><div class="card-title"><span class="mark-ok">${I.check}</span>Что получилось</div>${L.student.good.length ? ul(L.student.good) : '<div class="muted">В этот раз темы материала почти не прозвучали.</div>'}</div>
       <div class="card"><div class="card-title"><span class="t-yellow">${I.info}</span>Что стоит повторить</div>${repeatHtml}</div>
       ${L.two_speakers ? `<h2 style="font-size:16px;margin-top:8px">Вопросы и ответы по порядку</h2>${flowHtml(L, true)}` : ''}`;
  shell('#/home', `${head}<div class="stack">${parent ? '' : playerHtml(L)}${tiles(L, ['Получается', 'Почти получилось', 'Нужно повторить'])}<div class="grid2"><div class="stack">${body}</div>
    <div class="stack">${topicsSide(L)}<div class="card soft"><b>${parent ? 'Карта знаний' : 'Посмотри карту знаний'}</b><div class="muted small" style="margin:4px 0 8px">${parent ? 'Как меняются темы от урока к уроку' : 'Там видно, как меняются твои темы'}</div><a href="#/map" class="small">Открыть карту знаний</a></div></div></div></div>`);
  if (!parent) mountPlayer(L);
}

// Knowledge map with a per-lesson filter: the map can be shown as it was at the end of any lesson.
let mapSel = {};      // per subject: which lesson and which status is chosen
let mapRedraw = null;
const mapSelOf = (si) => (mapSel[si] ||= { lesson: 'all', status: 'all' });
const TL = { red: 'Не усвоено', yellow: 'Требует закрепления', green: 'Закреплено', gray: 'Не затрагивалась' };
const SL = { red: 'Нужно повторить', yellow: 'Почти получилось', green: 'Получается', gray: 'Ещё не было на уроках' };
const colorOf = (v) => (v == null ? 'gray' : v >= 80 ? 'green' : v >= 50 ? 'yellow' : 'red');
const lessonsOf = (lessons, subject) => lessons.filter((l) => l.subject_name === subject && l.status === 'done').sort((a, b) => a.date.localeCompare(b.date) || a.id - b.id);

function asOf(m, ls, sel) {
  const pos = sel.lesson === 'all' ? ls.length - 1 : ls.findIndex((l) => l.id === sel.lesson);
  const allowed = new Set(ls.slice(0, pos + 1).map((l) => l.id));
  return m.topics.map((t) => {
    const h = t.history.filter((x) => allowed.has(x.lesson_id)), cur = h[h.length - 1], prev = h[h.length - 2];
    const idx = cur ? cur.idx : null, color = colorOf(idx);
    return { ...t, index: idx, color, change: prev ? idx - prev.idx : null, last_lesson_id: cur ? cur.lesson_id : null, last_date: cur ? cur.date : null,
      missing: cur ? cur.missing : [], here: sel.lesson !== 'all' && !!cur && cur.lesson_id === sel.lesson, teacher_label: TL[color], student_label: SL[color] };
  });
}

function mapFilter(si, ls, sel, all, labels) {
  const chip = (id, label, sub) => `<button class="lf ${sel.lesson === id ? 'on' : ''}" data-act="map-lesson" data-s="${si}" data-l="${id}"><b>${label}</b><small>${sub}</small></button>`;
  const n = (c) => all.filter((t) => t.color === c).length;
  const st = (v, label, dot, count) => `<button class="sf ${sel.status === v ? 'on' : ''}" data-act="map-status" data-s="${si}" data-v="${v}">${dot ? `<i class="dot c-${dot}"></i>` : ''}${label} <span>${count}</span></button>`;
  const l = sel.lesson === 'all' ? null : ls.find((x) => x.id === sel.lesson), here = all.filter((t) => t.here).length;
  return `<div class="lf-row">${chip('all', 'Весь курс', 'итог сейчас')}${ls.map((x, i) => chip(x.id, `Урок ${i + 1}`, fdate(x.date))).join('')}</div>
    <div class="sf-row">${st('all', 'Все темы', null, all.length)}${st('red', labels.red, 'red', n('red'))}${st('yellow', labels.yellow, 'yellow', n('yellow'))}${st('green', labels.green, 'green', n('green'))}${st('gray', labels.gray, 'gray', n('gray'))}</div>
    ${l ? `<div class="banner" style="margin-top:12px">${I.info}<span><b>${e(l.title)}</b> · ${fdate(l.date)}. Карта показана на конец этого урока. На нём обсуждали ${here} ${plural(here, 'тему', 'темы', 'тем')}${l.index != null ? `, итог урока ${l.index} %` : ''}.</span><a class="end" href="#/lessons/${l.id}">Открыть отчёт</a></div>` : ''}`;
}

const redraw = async () => { const y = window.scrollY; await mapRedraw(); window.scrollTo(0, y); };

async function mapPage() {
  const parent = me.role === 'parent';
  mapSel = {};
  const d = await api('/my/home' + (parent && childId ? '?child=' + childId : ''));
  const card = (t) => { const color = t.color;
    return `<div class="map-card ${color} ${t.here ? 'here' : ''}"><div class="spread"><b>${e(t.title)}</b><span class="num t-${color}">${t.index} %</span></div>
      <div style="display:flex;margin:10px 0 8px">${bar(t.index, color)}</div>${t.here ? '<div style="margin-bottom:6px"><span class="pill blue">Обсуждали на этом уроке</span></div>' : ''}
      <div class="muted small">${t.here ? 'Урок' : 'Последний раз на уроке'} ${t.last_lesson_id ? `<a href="#/lessons/${t.last_lesson_id}">${fdate(t.last_date)}</a>` : ''}${t.change ? ` · <span class="${t.change > 0 ? 't-green' : 't-red'}">${t.change > 0 ? '↑ +' : '↓ '}${t.change} %</span>` : ''}</div>
      ${t.missing.length && color !== 'green' ? `<div class="muted small" style="margin-top:6px">${parent ? 'Не прозвучало' : 'Повтори'}: ${e(t.missing[0])}</div>` : ''}</div>`; };
  const col = (list, color) => `<div><div class="col-title"><i class="dot c-${color}"></i>${SL[color]} <span class="muted">${list.length}</span></div>
    ${list.sort((a, b) => b.here - a.here).map(card).join('') || '<div class="muted small">Нет тем</div>'}</div>`;
  const draw = () => shell('#/map', `<div class="head"><div><h1>Карта знаний</h1><div class="sub">${parent && d.child ? e(d.child.name) + ': темы и то, как они получаются' : 'Темы и то, как хорошо они у тебя получаются'}. Выбери урок, чтобы увидеть карту на тот момент.</div></div></div>
    ${d.maps.map((m, si) => { const ls = lessonsOf(d.lessons, m.subject), sel = mapSelOf(si), all = asOf(m, ls, sel);
      const colors = sel.status === 'all' ? ['red', 'yellow', 'green'] : sel.status === 'gray' ? [] : [sel.status];
      const later = all.filter((t) => t.index == null);
      return `<div class="card" style="margin-bottom:20px"><h2 style="font-size:16px;margin:0 0 12px">${e(m.subject)}</h2>${mapFilter(si, ls, sel, all, SL)}
        ${colors.length ? `<div class="cols3" style="margin-top:16px;${colors.length === 1 ? 'grid-template-columns:repeat(auto-fill,minmax(260px,1fr))' : ''}">${colors.map((c) => col(all.filter((t) => t.color === c), c)).join('')}</div>` : ''}
        ${later.length && (sel.status === 'all' || sel.status === 'gray') ? `<div class="muted small" style="margin:14px 0 0"><b>Ещё не было на уроках${sel.lesson === 'all' ? '' : ' к этому моменту'}:</b> ${later.map((t) => e(t.title)).join(', ')}</div>` : ''}</div>`; }).join('') || '<div class="card empty">Пока нет предметов</div>'}
    <div class="banner">${I.info}<span>Процент показывает, насколько тема усвоена по последнему уроку, где она обсуждалась. Красный — ниже 50 %, жёлтый — 50–79 %, зелёный — от 80 %.</span></div>`);
  mapRedraw = draw; draw();
}

// ---------------------------------------------------------------- system admin

async function adminPage() {
  const d = await api('/admin/settings'), c = d.settings;
  const sel = (name, opts, cur) => `<select class="in" name="${name}">${opts.map(([v, l]) => `<option value="${e(v)}" ${v === cur ? 'selected' : ''}>${e(l)}</option>`).join('')}</select>`;
  const W = { 'base-ru-finetuned': 'base-ru · 74 млн, дообучена вами на русской речи', tiny: 'tiny · 39 млн, самая быстрая', base: 'base · 74 млн', small: 'small · 244 млн, по умолчанию', medium: 'medium · 769 млн', turbo: 'turbo · 809 млн, быстрая и точная', 'large-v3': 'large-v3 · 1550 млн, как в дипломе' };
  shell('#/admin', `<div class="head"><div><h1>Модели и анализ</h1><div class="sub">Настройки применяются к новым записям и к кнопке «Пересчитать анализ». Версия промпта: ${e(d.prompt_version)}</div></div>
      <button class="btn primary" data-act="save-settings">Сохранить</button></div>
    <form id="set-form" class="stack">
    <div class="card"><div class="card-title">${I.lessons} Распознавание речи: Whisper</div><div class="form-grid">
      <div><label class="f">Модель</label>${sel('whisper_model', d.whisper_models.map((m) => [m, W[m] || m]), c.whisper_model)}<div class="muted small hint">Больше модель — точнее текст и дольше обработка. Новая модель скачается при первом использовании.</div></div>
      <div><label class="f">Язык речи</label>${sel('whisper_language', [['auto', 'Определять автоматически'], ['ru', 'Русский'], ['en', 'English'], ['kk', 'Қазақша']], c.whisper_language)}<div class="muted small hint">Для смешанной речи оставьте автоопределение.</div></div></div></div>
    <div class="card"><div class="card-title">${I.chip} Кто анализирует ответы</div>
      <label class="opt"><input type="radio" name="analysis_mode" value="llm" ${c.analysis_mode === 'llm' ? 'checked' : ''}><div><b>Языковая модель (LLM)</b><small>Сверяет ответы ученика с материалом по смыслу, пишет комментарии и три отчёта. Нужен ключ или локальная модель.</small></div></label>
      <label class="opt"><input type="radio" name="analysis_mode" value="embeddings" ${c.analysis_mode === 'embeddings' ? 'checked' : ''}><div><b>Эмбеддинги без LLM</b><small>Работает без интернета и ключа. Проверяет только, прозвучала ли тема; тексты отчётов собираются по шаблону.</small></div></label></div>
    <div class="card"><div class="card-title">${I.settings} Языковая модель</div><div class="form-grid">
      <div><label class="f">Сервис</label>${sel('llm_provider', Object.entries(d.presets).map(([k, v]) => [k, v.label]), c.llm_provider)}<div class="muted small hint" id="key-link"></div></div>
      <div><label class="f">Модель</label><input class="in" name="llm_model" value="${e(c.llm_model)}" list="models-list"><datalist id="models-list"></datalist><div class="hint"><button type="button" class="link-btn small" data-act="load-models">Показать доступные модели</button></div></div>
      <div><label class="f">Адрес API</label><input class="in" name="llm_base_url" value="${e(c.llm_base_url)}"></div>
      <div><label class="f">API-ключ</label><input class="in" name="llm_api_key" type="password" autocomplete="off" placeholder="${d.key_set ? 'сохранён: ' + e(d.key_hint || 'из переменной окружения') : 'вставьте ключ'}"><div class="muted small hint">Хранится только в базе на этом компьютере. Пустое поле оставляет сохранённый ключ.</div></div>
      <div><label class="f">Температура</label><input class="in" name="llm_temperature" type="number" step="0.1" min="0" max="1.5" value="${e(c.llm_temperature)}"><div class="muted small hint">Ниже — стабильнее оценки.</div></div>
      <div><label class="f">Язык отчётов</label>${sel('report_language', [['ru', 'Русский'], ['en', 'English']], c.report_language)}</div></div>
      <div class="row" style="margin-top:16px;flex-wrap:wrap"><button type="button" class="btn" data-act="test-llm">Проверить подключение</button><span id="test-out" class="small"></span></div>
      <div class="banner" style="margin-top:14px">${I.info}<span>В модель уходит только текст расшифровки, имена заменяются метками «Ученик» и «Преподаватель». Аудио компьютер не покидает.</span></div></div>
    <div class="card"><div class="card-title">Правила</div><div class="form-grid">
      <div><label class="f">Порог сходства для эмбеддингов</label><input class="in" name="threshold" type="number" step="0.05" min="0.3" max="0.95" value="${e(c.threshold)}"></div>
      <div><label class="f">Долгая пауза перед ответом, с</label><input class="in" name="pause_seconds" type="number" step="1" min="1" max="60" value="${e(c.pause_seconds)}"></div></div></div>
    </form>`);
  const f = $('#set-form'), P = d.presets;
  const link = () => { const p = P[f.llm_provider.value]; $('#key-link').innerHTML = p.key_url ? `${p.needs_key ? 'Ключ выдаётся здесь' : 'Установка'}: <a href="${e(p.key_url)}" target="_blank" rel="noopener">${e(p.key_url.replace('https://', ''))}</a>` : 'Укажите адрес и модель вручную'; };
  f.llm_provider.onchange = () => { const p = P[f.llm_provider.value]; f.llm_base_url.value = p.base_url; f.llm_model.value = p.model; link(); };
  link();
}

const formValues = () => Object.fromEntries(new FormData($('#set-form')));

async function queuePage() {
  const d = await api('/admin/queue');
  const rows = d.lessons.map((l) => `<tr><td><b>${e(l.title)}</b><div class="muted small">${e(l.student_name)} · ${e(l.subject_name)}</div></td><td>${lessonStatus(l)}${l.status === 'error' ? `<div class="small t-red" style="max-width:260px">${e(l.error)}</div>` : ''}</td>
    <td class="small">${l.whisper ? 'Whisper ' + e(l.whisper) : ''}<div class="muted">${l.engine === 'llm' ? e(l.llm_model) : l.engine ? 'эмбеддинги' : ''}${l.llm_error ? ' · <span class="t-red" title="' + e(l.llm_error) + '">LLM не ответила</span>' : ''}</div></td>
    <td class="small muted">${l.timings ? `речь ${l.timings.asr} с${l.timings.diarization != null ? ` · голоса ${l.timings.diarization} с` : ''}${l.timings.llm != null ? ` · LLM ${l.timings.llm} с` : ''}` : ''}</td>
    <td style="text-align:right;white-space:nowrap">${l.status === 'done' ? `<a href="#/lessons/${l.id}">Отчёт</a> · <button class="link-btn" data-act="reanalyse" data-id="${l.id}">Пересчитать анализ</button> · ` : ''}${l.status === 'done' || l.status === 'error' ? `<button class="link-btn" data-act="retry" data-id="${l.id}">Обработать заново</button>` : ''}</td></tr>`).join('');
  shell('#/queue', `<div class="head"><div><h1>Очередь и ошибки</h1><div class="sub">Все записи, какими моделями обработаны и сколько это заняло. В очереди сейчас: ${d.waiting}</div></div></div>
    <div class="card flush">${rows ? `<table><tr><th>Урок</th><th>Статус</th><th>Модели</th><th>Время</th><th></th></tr>${rows}</table>` : '<div class="empty">Записей пока нет</div>'}</div>`);
  pollIfBusy(d.lessons);
}


// ---------------------------------------------------------------- charts and shared blocks

function trendChart(points) {
  if (!points.length) return '<div class="muted">График появится после первого разобранного урока.</div>';
  const W = 640, H = 200, L = 34, R = 30, T = 12, B = 34, iw = W - L - R, ih = H - T - B;
  const X = (i) => L + (points.length === 1 ? iw / 2 : (iw * i) / (points.length - 1)), Y = (v) => T + ih * (1 - v / 100);
  const col = (v) => (v >= 80 ? 'green' : v >= 50 ? 'yellow' : 'red');
  const grid = [0, 50, 80, 100].map((v) => `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" class="gl"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end" class="ax">${v}</text>`).join('');
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(p.index).toFixed(1)}`).join(' ');
  const every = Math.ceil(points.length / 6);
  const dots = points.map((p, i) => `<circle cx="${X(i).toFixed(1)}" cy="${Y(p.index).toFixed(1)}" r="5" class="dt ${col(p.index)}"><title>${e(p.title)}: ${p.index} %</title></circle>
    ${i % every === 0 || i === points.length - 1 ? `<text x="${X(i).toFixed(1)}" y="${H - 12}" text-anchor="middle" class="ax">${fdate(p.date)}</text>` : ''}`).join('');
  return `<svg viewBox="0 0 ${W} ${H}" class="trend"><rect x="${L}" y="${Y(100)}" width="${iw}" height="${Y(80) - Y(100)}" class="band green"/>
    <rect x="${L}" y="${Y(80)}" width="${iw}" height="${Y(50) - Y(80)}" class="band yellow"/><rect x="${L}" y="${Y(50)}" width="${iw}" height="${Y(0) - Y(50)}" class="band red"/>
    ${grid}<path d="${line}" class="ln"/>${dots}</svg>`;
}

const spark = (vals) => {
  if (vals.length < 2) return '<span class="muted small">нет данных</span>';
  const W = 90, H = 26, X = (i) => (W * i) / (vals.length - 1), Y = (v) => 3 + (H - 6) * (1 - v / 100);
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><path d="${vals.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--blue)" stroke-width="2" stroke-linejoin="round"/></svg>`;
};

const RISK = { high: ['red', 'Нужна помощь'], mid: ['yellow', 'Следить'], ok: ['green', 'Всё в порядке'], none: ['gray', 'Нет данных'] };

function progressCard(d, parent) {
  const tr = d.trend || [], last = tr[tr.length - 1], prev = tr[tr.length - 2];
  const stuck = d.stuck && d.stuck.length ? `<div class="banner warn" style="margin-top:12px">${I.info}<span>${parent ? 'Эти темы не получаются уже несколько уроков подряд: ' : 'Эти темы пока не получаются несколько уроков подряд: '}<b>${d.stuck.map((t) => e(t.title)).join(', ')}</b>. ${parent ? 'Стоит обсудить с преподавателем, как помочь.' : 'Попроси преподавателя разобрать их ещё раз.'}</span></div>` : '';
  return `<div class="card" style="margin-bottom:24px"><div class="spread"><div><div class="card-title" style="margin:0">Динамика</div><div class="muted small">Как менялся результат от урока к уроку</div></div>
    ${last ? `<div style="text-align:right"><b style="font-size:22px">${last.index} %</b><div class="small">${prev ? changeText(last.index - prev.index) : 'первый урок'}</div></div>` : ''}</div>${stuck}<div style="margin-top:8px">${trendChart(tr)}</div></div>`;
}

function parentsCard(s, all) {
  const free = all.filter((p) => !s.parents.some((x2) => x2.id === p.id));
  return `<div class="card"><div class="spread"><div class="card-title" style="margin:0">Родители</div><button class="btn sm" data-act="add-parent" data-student="${s.id}">${I.plus} Новый</button></div>
    <div class="stack" style="margin-top:12px;gap:10px">${s.parents.length ? s.parents.map((p) => `<div class="spread"><div class="row"><div class="avatar">${e(initials(p.name))}</div><div><b class="small">${e(p.name)}</b><div class="muted small">${e(p.email)}</div></div></div>
      <button class="icon-btn" title="Отвязать" data-act="detach" data-parent="${p.id}" data-student="${s.id}">${I.x}</button></div>`).join('') : '<div class="muted small">Родитель не привязан. Он увидит отчёты ребёнка простым языком, без профессиональных терминов.</div>'}</div>
    ${free.length ? `<div class="row" style="margin-top:14px"><select class="in" id="ex-parent" style="flex:1">${free.map((p) => `<option value="${p.id}">${e(p.name)}</option>`).join('')}</select><button class="btn sm" data-act="attach-existing" data-student="${s.id}">Привязать</button></div>` : ''}</div>`;
}

// ---------------------------------------------------------------- parents

async function addParentDialog(studentId) {
  const students = await api('/students');
  if (!students.length) return toast('Сначала добавьте ученика');
  modal(`<h2>Новый родитель</h2><form id="pr-form"><label class="f">Имя и фамилия</label><input class="in" name="name" required>
    <label class="f">Электронная почта (логин)</label><input class="in" name="email" type="email" required>
    <label class="f">Пароль для входа</label><input class="in" name="password" type="text" minlength="6" required>
    <label class="f">Чьи отчёты увидит родитель</label><div class="checks">${students.map((s) => `<label><input type="checkbox" name="kid" value="${s.id}" ${String(s.id) === String(studentId) ? 'checked' : ''}> ${e(s.name)}</label>`).join('')}</div>
    <div class="err" id="pr-err"></div><div class="actions"><button type="button" class="btn" data-act="close">Отмена</button><button class="btn primary">Создать</button></div></form>`);
  $('#pr-form').onsubmit = async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    try { await api('/parents', { json: { name: f.get('name'), email: f.get('email'), password: f.get('password'), student_ids: f.getAll('kid').map(Number) } }); closeModal(); toast('Родитель создан и привязан'); route(); }
    catch (err) { $('#pr-err').textContent = err.message; }
  };
}

async function attachChildDialog(parentId) {
  const [students, parents] = await Promise.all([api('/students'), api('/parents')]);
  const p = parents.find((x2) => String(x2.id) === String(parentId));
  const free = students.filter((s) => !p.children.some((c) => c.id === s.id));
  if (!free.length) return toast('Все ваши ученики уже привязаны');
  modal(`<h2>Привязать ребёнка</h2><p class="muted">${e(p.name)} сможет смотреть уроки и отчёты выбранного ученика.</p>
    <select class="in" id="kid-sel">${free.map((s) => `<option value="${s.id}">${e(s.name)}</option>`).join('')}</select>
    <div class="actions"><button class="btn" data-act="close">Отмена</button><button class="btn primary" id="kid-ok">Привязать</button></div>`);
  $('#kid-ok').onclick = async () => { try { await api(`/parents/${parentId}/children`, { json: { student_id: $('#kid-sel').value } }); closeModal(); toast('Ребёнок привязан'); route(); } catch (err) { toast(err.message); } };
}

async function parentsPage() {
  const list = await api('/parents');
  const rows = list.map((p) => `<tr><td><div class="row"><div class="avatar">${e(initials(p.name))}</div><div><b>${e(p.name)}</b><div class="muted small">${e(p.email)}</div></div></div></td>
    <td><div class="chips">${p.children.map((c) => `<span class="pill blue"><a href="#/students/${c.id}">${e(c.name)}</a><button class="icon-btn mini" title="Отвязать" data-act="detach" data-parent="${p.id}" data-student="${c.id}">${I.x}</button></span>`).join('') || '<span class="muted small">никого</span>'}</div></td>
    <td style="text-align:right"><button class="btn sm" data-act="attach-child" data-parent="${p.id}">${I.plus} Ребёнок</button></td></tr>`).join('');
  shell('#/parents', `<div class="head"><div><h1>Родители</h1><div class="sub">Родитель входит в свой кабинет и видит отчёты только привязанных детей</div></div>
    <button class="btn primary" data-act="add-parent">${I.plus} Добавить родителя</button></div>
    <div class="card flush">${list.length ? `<table><tr><th>Родитель</th><th>Дети</th><th></th></tr>${rows}</table>` : '<div class="empty">Родителей пока нет. Создайте аккаунт и выберите ребёнка.</div>'}</div>`);
}

// ---------------------------------------------------------------- overview

async function overviewPage() {
  const d = await api('/overview'), t = d.totals;
  const tile = (label, value, hint) => `<div class="card stat"><small>${label}</small><div>${value}</div>${hint ? `<span class="muted small">${hint}</span>` : ''}</div>`;
  const rows = d.people.map((p) => {
    const [c, label] = RISK[p.risk];
    return `<tr class="click" data-go="#/students/${p.id}"><td><div class="row"><div class="avatar">${e(initials(p.name))}</div><b>${e(p.name)}</b></div></td>
      <td>${pill(c, label)}${p.stuck.length ? `<div class="small t-red" style="margin-top:4px">Застрял: ${e(p.stuck.slice(0, 2).join(', '))}</div>` : ''}</td>
      <td><span class="num">${p.avg == null ? 'нет' : p.avg + ' %'}</span> ${p.delta == null ? '' : changeText(p.delta)}</td><td>${spark(p.trend)}</td></tr>`;
  }).join('');
  const weak = d.weak_topics.map((w) => `<div class="repeat yellow"><div class="spread"><b>${e(w.title)}</b><span class="pill gray">${w.count} ${plural(w.count, 'ученик', 'ученика', 'учеников')}</span></div>
    <div class="muted small">${e(w.subject)} · ${e(w.students.slice(0, 3).join(', '))}</div></div>`).join('');
  const recent = d.recent.map((l) => `<div class="spread" style="padding:8px 0;border-bottom:1px solid #eef0f3"><div><b class="small">${e(l.title)}</b><div class="muted small">${e(l.student_name)} · ${fdate(l.date)}</div></div>
    ${l.status === 'done' ? `<a href="#/lessons/${l.id}" class="small">${l.index == null ? 'Отчёт' : l.index + ' %'}</a>` : lessonStatus(l)}</div>`).join('');
  shell('#/overview', `<div class="head"><div><h1>Обзор</h1><div class="sub">Кому нужна помощь, какие темы не даются и что загружено недавно</div></div>
    <a class="btn primary" href="#/upload">${I.upload} Загрузить запись</a></div>
    <div class="stats four">${tile('Учеников', t.students, `родителей: ${t.parents}`)}${tile('Разобрано уроков', t.lessons)}${tile('Средний индекс', t.avg == null ? 'нет' : t.avg + ' %')}${tile('Требуют внимания', t.attention, 'красные и застрявшие темы')}</div>
    <div class="grid2"><div class="card flush"><div class="card-title" style="padding:16px 20px 0">Ученики по уровню внимания</div>${rows ? `<table><tr><th>Ученик</th><th>Состояние</th><th>Индекс</th><th>Динамика</th></tr>${rows}</table>` : '<div class="empty">Добавьте первого ученика</div>'}</div>
      <div class="stack"><div class="card"><div class="card-title">Темы, которые не даются</div><div class="stack" style="gap:10px">${weak || '<div class="muted">Пока все темы усваиваются хорошо.</div>'}</div></div>
      <div class="card"><div class="card-title">Недавние уроки</div>${recent || '<div class="muted">Записей пока нет</div>'}</div></div></div>`);
  pollIfBusy(d.recent);
}

// ---------------------------------------------------------------- profile

async function profilePage() {
  const role = ROLE[me.role][1];
  shell('#/profile', `<div class="head"><div><h1>Профиль</h1><div class="sub">${e(role)} · ${e(me.email)}</div></div></div>
    <div class="card" style="max-width:560px"><form id="pf-form"><label class="f" style="margin-top:0">Имя и фамилия</label><input class="in" name="name" value="${e(me.name)}" required>
    <label class="f">Электронная почта</label><input class="in" value="${e(me.email)}" disabled>
    <div class="divider">смена пароля</div><label class="f" style="margin-top:0">Текущий пароль</label><input class="in" type="password" name="old_password" autocomplete="current-password">
    <label class="f">Новый пароль (от 6 символов)</label><input class="in" type="password" name="new_password" autocomplete="new-password">
    <div class="err" id="pf-err"></div><button class="btn primary">Сохранить</button></form></div>`);
  $('#pf-form').onsubmit = async (ev) => {
    ev.preventDefault();
    try { await api('/profile', { json: Object.fromEntries(new FormData(ev.target)) }); me = await api('/me'); toast('Профиль сохранён'); route(); }
    catch (err) { $('#pf-err').textContent = err.message; }
  };
}


// ---------------------------------------------------------------- Whisper check: the original model and the fine-tuned one side by side

const WH_LABELS = { tiny: 'tiny · 39 млн', base: 'base · 74 млн (обычный)', small: 'small · 244 млн', medium: 'medium · 769 млн', turbo: 'turbo · 809 млн', 'large-v3': 'large-v3 · 1550 млн', 'base-ru-finetuned': 'base-ru · дообучена вами' };

async function whisperPage() {
  const ex = await api('/whisper/examples');
  const item = (x) => `<div class="spread" style="padding:9px 0;border-bottom:1px solid #eef0f3;gap:14px"><div><div class="small">${e(x.text)}</div><div class="muted small">${x.seconds} с${x.before != null ? ` · обычный ${(x.before * 100).toFixed(0)} % ошибок → дообученный ${(x.after * 100).toFixed(0)} %` : ''}</div></div><button class="btn sm" data-act="wh-example" data-id="${e(x.id)}">Проверить</button></div>`;
  const rows = (ex.better.length ? `<div class="small" style="margin:8px 0 2px"><b>Где дообучение помогло больше всего</b></div>${ex.better.map(item).join('')}` : '') + (ex.worse.length ? `<div class="small" style="margin:16px 0 2px"><b>Где стало хуже (для честности)</b></div>${ex.worse.map(item).join('')}` : '');
  shell('#/whisper', `<div class="head"><div><h1>Проверка Whisper</h1><div class="sub">Одна и та же запись через обычный Whisper-base и через модель, дообученную вами на русской речи. Если известен правильный текст, показывается доля ошибочных слов (WER): чем меньше, тем лучше.</div></div></div>
    ${ex.model_ready ? '' : `<div class="banner warn">${I.info}<span>Файл дообученной модели не найден: <code>whisper-finetune/models/whisper-base-ru.pt</code>. Его создают шаги 05 и 08 в папке whisper-finetune.</span></div>`}
    <div class="card" style="margin-bottom:20px"><div class="card-title">Две записи, две модели</div>
      <div class="muted small" style="margin-bottom:10px">Загрузите запись в каждую часть и выберите для неё модель Whisper. Если нужно сравнить модели на одном и том же звуке, загрузите запись только в A и отметьте «та же запись».</div>
      <form id="pair-form"><div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">${['a', 'b'].map((k) => `<div class="card soft" style="margin:0"><b>Запись ${k.toUpperCase()}</b>
        <label class="f">Файл (аудио или видео, до 3 минут)</label><input class="in" type="file" name="file_${k}" accept="audio/*,video/*,.m4a,.mkv" style="height:auto;padding:8px">
        ${k === 'b' ? '<label class="row small" style="margin:8px 0 0;gap:8px;font-weight:400"><input type="checkbox" name="same_audio" value="1" id="same-audio"> та же запись, что в A</label>' : ''}
        <label class="f">Модель Whisper</label><select class="in" name="model_${k}">${ex.models.map((m) => `<option value="${e(m)}" ${m === (k === 'a' ? 'base' : 'base-ru-finetuned') ? 'selected' : ''}>${e(WH_LABELS[m] || m)}</option>`).join('')}</select>
        <label class="f">Правильный текст (необязательно)</label><textarea class="in" name="reference_${k}" rows="2" placeholder="Если вставить текст, посчитаю долю ошибок"></textarea></div>`).join('')}</div>
        <div class="row" style="margin-top:14px;gap:14px"><button class="btn primary" id="pair-btn">Сравнить</button><label class="small row" style="gap:8px;font-weight:400">Язык записей
        <select class="in" name="language" style="width:150px"><option value="ru">Русский</option><option value="en">English</option><option value="auto">Определить</option></select></label>
        <label class="small row" style="gap:6px;font-weight:400"><input type="checkbox" name="split_roles" value="1" checked> разделить на преподавателя и ученика</label><span class="small muted">Большие модели (small, medium, large-v3) считают заметно дольше.</span></div><div class="err" id="pair-err"></div></form><div id="pair-out" style="margin-top:16px"></div></div>
    <div class="grid2"><div class="stack"><div class="card"><div class="card-title">Своя запись</div><form id="wh-form"><label class="f" style="margin-top:0">Аудио или видео (до 3 минут, по-русски)</label>
        <input class="in" type="file" name="file" accept="audio/*,video/*,.m4a,.mkv" required style="height:auto;padding:8px"><label class="f">Правильный текст (необязательно)</label>
        <textarea class="in" name="reference" rows="3" placeholder="Если вставить текст, который произносится в записи, я посчитаю WER для обеих моделей"></textarea>
        <div class="err" id="wh-err"></div><button class="btn primary" id="wh-btn">Сравнить</button></form></div>
      <div class="card"><div class="card-title">Примеры из теста</div><div class="muted small" style="margin-bottom:6px">Русская речь из набора FLEURS. Эти записи модель при обучении не видела, правильный текст известен. В среднем по всем 500 фразам разница небольшая (24,8 % и 24,1 % ошибок), но на отдельных фразах она заметна в обе стороны.</div>${rows || '<div class="muted">Тестовый набор не найден (папка whisper-finetune/data).</div>'}</div></div>
    <div class="card" id="wh-out"><div class="muted">Результат появится здесь. Первая проверка идёт дольше: загружаются две модели.</div></div></div>`);
  const run = async (body) => {
    $('#wh-err').textContent = ''; $('#wh-out').innerHTML = '<span class="spin"></span> Распознаю запись двумя моделями...';
    document.querySelectorAll('#wh-btn, [data-act=wh-example]').forEach((b) => { b.disabled = true; });
    try { show(await api('/whisper/compare', { method: 'POST', body })); }
    catch (err) { $('#wh-out').innerHTML = `<div class="t-red">${e(err.message)}</div>`; }
    document.querySelectorAll('#wh-btn, [data-act=wh-example]').forEach((b) => { b.disabled = false; });
  };
  const tok = (w) => w.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  const mark = (ref, hyp) => {              // the words of the answer that do not match the correct text (longest common subsequence), in red
    const r = tok(ref), words = hyp.split(/\s+/).filter(Boolean), h = [], owner = [];
    words.forEach((w, i) => tok(w).forEach((t) => { h.push(t); owner.push(i); }));
    const L = Array.from({ length: r.length + 1 }, () => new Array(h.length + 1).fill(0));
    for (let i = r.length - 1; i >= 0; i--) for (let j = h.length - 1; j >= 0; j--) L[i][j] = r[i] === h[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    const bad = new Set(owner.map((_, k) => k)); let i = 0, j = 0;
    while (i < r.length && j < h.length) { if (r[i] === h[j]) { bad.delete(j); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) i++; else j++; }
    const wrong = new Set([...bad].map((k) => owner[k]));
    return words.map((w, k) => (wrong.has(k) ? `<span style="background:#fecaca;border-radius:3px;padding:0 2px">${e(w)}</span>` : e(w))).join(' ');
  };
  const show = (r) => {
    const w = r.results.map((x) => x.wer).filter((v) => v != null), best = w.length ? Math.min(...w) : null;
    const cards = r.results.map((x) => `<div class="card soft" style="margin-bottom:12px"><div class="spread"><b>${e(x.label)}</b><span class="small muted">${x.seconds} с</span></div>
      <div style="margin:8px 0;font-size:15px">${x.text ? (r.reference ? mark(r.reference, x.text) : e(x.text)) : '<span class="muted">пусто</span>'}</div>${x.wer != null ? `<span class="pill ${x.wer === best && w.length > 1 && w[0] !== w[1] ? 'green' : 'gray'}">WER ${(x.wer * 100).toFixed(1)} %</span>` : ''}</div>`).join('');
    const diff = w.length === 2 ? (w[0] - w[1]) * 100 : null;
    $('#wh-out').innerHTML = `<div class="card-title">Результат · запись ${r.duration} с</div>${r.reference ? `<div class="card soft" style="margin-bottom:12px"><div class="muted small">Правильный текст</div><div style="font-size:15px">${e(r.reference)}</div></div>` : ''}${cards}
      ${diff == null ? '' : `<div class="banner" style="margin-top:6px">${I.info}<span>${Math.abs(diff) < 0.05 ? 'WER одинаковый.' : diff > 0 ? `Дообученная модель ошиблась реже: разница ${diff.toFixed(1)} п. п.` : `Обычная модель ошиблась реже: разница ${(-diff).toFixed(1)} п. п.`} Красным отмечены слова, которых нет в правильном тексте. Одна запись мало что доказывает: на 500 тестовых фразах разница небольшая и статистически незначимая (WER 24,8 % и 24,1 %).</span></div>`}`;
  };
  const pairShow = (r) => {
    const [A, B] = r.results, same = r.same_audio;
    const card = (x, other) => {
      const ref = x.reference || '', text = x.text;
      const against = ref || other.text, show = (txt) => mark(against, txt);        // no correct text: the words that differ from the other transcript
      const body = !text ? '<span class="muted">пусто</span>' : x.turns
        ? `<div class="stack" style="gap:8px">${x.turns.map((u) => `<div style="padding:8px 12px;border-radius:10px;background:${u.speaker === 'teacher' ? '#e0e9ff' : '#e7f6ec'};${u.speaker === 'teacher' ? '' : 'margin-left:22px'}"><div class="small" style="font-weight:600;color:${u.speaker === 'teacher' ? '#254fca' : '#15803d'}">${u.speaker === 'teacher' ? 'Преподаватель' : 'Ученик'} · ${u.start} с</div><div style="font-size:15px">${show(u.text)}</div></div>`).join('')}</div>`
        : show(text);
      return `<div class="card soft" style="margin:0"><div class="spread"><b>Запись ${x.slot} · ${e(WH_LABELS[x.model] || x.model)}</b><span class="small muted">${x.duration} с записи</span></div>
        <div style="margin:10px 0;font-size:15px">${body}</div><div class="row" style="gap:8px;flex-wrap:wrap"><span class="pill gray">распознавание ${x.seconds} с</span><span class="pill gray">загрузка модели ${x.load_seconds} с</span>${x.turns ? `<span class="pill blue">реплик: ${x.turns.length}</span>` : ''}
        ${x.wer != null ? `<span class="pill ${x.wer <= 0.1 ? 'green' : x.wer <= 0.25 ? 'yellow' : 'red'}">WER ${(x.wer * 100).toFixed(1)} %</span>` : ''}</div></div>`;
    };
    const note = A.wer != null && B.wer != null ? (A.wer === B.wer ? 'Доля ошибок одинаковая.' : `Меньше ошибок у записи ${A.wer < B.wer ? 'A' : 'B'} (${((Math.abs(A.wer - B.wer)) * 100).toFixed(1)} п. п.).`)
      : same ? 'Красным отмечены слова, которых нет в расшифровке другой модели: так видно, где модели расходятся. Чтобы узнать, кто прав, вставьте правильный текст.' : 'Красным отмечены слова, которых нет в другой расшифровке. Вставьте правильный текст, чтобы получить долю ошибок.';
    $('#pair-out').innerHTML = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">${card(A, B)}${card(B, A)}</div><div class="banner" style="margin-top:12px">${I.info}<span>${note}</span></div>`;
  };
  $('#same-audio').onchange = (ev) => { $('#pair-form').elements.file_b.disabled = ev.target.checked; };
  $('#pair-form').onsubmit = async (ev) => {
    ev.preventDefault(); $('#pair-err').textContent = '';
    const f = new FormData(ev.target); if (f.get('file_a') && !f.get('file_a').name) f.delete('file_a'); if (f.get('file_b') && !f.get('file_b').name) f.delete('file_b');
    $('#pair-btn').disabled = true; $('#pair-out').innerHTML = '<span class="spin"></span> Распознаю обе записи. Загрузка больших моделей может занять около минуты...';
    try { pairShow(await api('/whisper/pair', { method: 'POST', body: f })); }
    catch (err) { $('#pair-out').innerHTML = ''; $('#pair-err').textContent = err.message; }
    $('#pair-btn').disabled = false;
  };
  $('#wh-form').onsubmit = (ev) => { ev.preventDefault(); run(new FormData(ev.target)); };
  document.querySelectorAll('[data-act=wh-example]').forEach((b) => { b.onclick = () => { const f = new FormData(); f.append('example_id', b.dataset.id); run(f); }; });
}

async function route() {
  clearTimeout(pollTimer);
  if (!me) { try { me = await api('/me'); } catch { return loginPage(); } }
  const [path, query = ''] = (location.hash || '').replace(/^#/, '').split('?');
  const p = path.split('/').filter(Boolean);
  const leavingLesson = !(p[0] === 'lessons' && p[1]);
  if (leavingLesson && audio) { audio.pause(); audio = null; }
  try {
    if (me.role === 'admin') {
      if (p[0] === 'lessons' && p[2] === 'transcript') return await transcriptPage(p[1]);
      if (p[0] === 'lessons' && p[2] === 'model') return await modelPage(p[1]);
      if (p[0] === 'lessons' && p[1]) return await lessonTeacherPage(p[1]);
      if (p[0] === 'queue') return await queuePage();
      return await adminPage();
    }
    if (p[0] === 'profile') return await profilePage();
    if (p[0] === 'whisper' && (me.role === 'teacher' || me.role === 'admin')) return await whisperPage();
    if (me.role === 'teacher') {
      if (p[0] === 'overview') return await overviewPage();
      if (p[0] === 'parents') return await parentsPage();
      if (p[0] === 'students' && p[1]) return await studentCardPage(p[1]);
      if (p[0] === 'lessons' && p[2] === 'transcript') return await transcriptPage(p[1]);
      if (p[0] === 'lessons' && p[2] === 'model') return await modelPage(p[1]);
      if (p[0] === 'lessons' && p[1]) return await lessonTeacherPage(p[1]);
      if (p[0] === 'lessons') return await lessonsPage();
      if (p[0] === 'upload') return await uploadPage(query);
      if (p[0] === 'subjects') return await subjectsPage();
      if (p[0] === 'students') return await studentsPage();
      return await overviewPage();
    }
    if (p[0] === 'lessons' && p[1]) return await lessonStudentPage(p[1]);
    if (p[0] === 'map') return await mapPage();
    return await homePage();
  } catch (err) {
    if (me) shell('', `<div class="card"><div class="card-title t-red">Не получилось открыть страницу</div><p>${e(err.message)}</p><a class="btn" href="#/">На главную</a></div>`);
  }
}

document.addEventListener('click', async (ev) => {
  const seekEl = ev.target.closest('[data-seek]');
  if (seekEl) return seek(+seekEl.dataset.seek);
  const act = ev.target.closest('[data-act]');
  if (!act) { const go = ev.target.closest('[data-go]'); if (go && !ev.target.closest('a,button')) location.hash = go.dataset.go; return; }
  const a = act.dataset.act;
  try {
    if (a === 'overlay') { if (ev.target === act) closeModal(); }
    else if (a === 'close') closeModal();
    else if (a === 'logout') { await api('/logout', { method: 'POST' }); me = null; location.hash = ''; route(); }
    else if (a === 'demo') { const d = await fetch('/api/demo-accounts').then((r) => r.json()); await doLogin(d[act.dataset.role].email, d[act.dataset.role].password); }
    else if (a === 'play') { if (audio) (audio.paused ? audio.play() : audio.pause()); }
    else if (a === 'speed') { const next = { 1: 1.5, 1.5: 2, 2: 1 }[audio.playbackRate] || 1; audio.playbackRate = next; act.textContent = next + '×'; }
    else if (a === 'add-student') await addStudentDialog();
    else if (a === 'map-lesson') { mapSelOf(act.dataset.s).lesson = act.dataset.l === 'all' ? 'all' : +act.dataset.l; await redraw(); }
    else if (a === 'map-status') { const m = mapSelOf(act.dataset.s); m.status = m.status === act.dataset.v ? 'all' : act.dataset.v; await redraw(); }
    else if (a === 'add-parent') await addParentDialog(act.dataset.student);
    else if (a === 'attach-child') await attachChildDialog(act.dataset.parent);
    else if (a === 'attach-existing') { const v = $('#ex-parent').value; if (v) { await api(`/parents/${v}/children`, { json: { student_id: act.dataset.student } }); toast('Родитель привязан'); route(); } }
    else if (a === 'detach') modal(`<h2>Отвязать ребёнка?</h2><p class="muted">Родитель перестанет видеть уроки и отчёты этого ученика. Аккаунт родителя останется.</p><div class="actions"><button class="btn" data-act="close">Отмена</button><button class="btn primary" data-act="detach-yes" data-parent="${act.dataset.parent}" data-student="${act.dataset.student}">Отвязать</button></div>`);
    else if (a === 'detach-yes') { await api(`/parents/${act.dataset.parent}/children/${act.dataset.student}`, { method: 'DELETE' }); closeModal(); toast('Ребёнок отвязан'); route(); }
    else if (a === 'add-subject') {
      modal(`<h2>Новый предмет</h2><form id="sj-form"><label class="f">Название</label><input class="in" name="name" required><div class="actions"><button type="button" class="btn" data-act="close">Отмена</button><button class="btn primary">Добавить</button></div></form>`);
      $('#sj-form').onsubmit = async (e2) => { e2.preventDefault(); await api('/subjects', { json: { name: new FormData(e2.target).get('name') } }); closeModal(); route(); };
    }
    else if (a === 'del-topic') { await api('/topics/' + act.dataset.id, { method: 'DELETE' }); toast('Тема удалена'); route(); }
    else if (a === 'retry') { await api(`/lessons/${act.dataset.id}/retry`, { method: 'POST' }); route(); }
    else if (a === 'confirm') { await api('/assessments/' + act.dataset.id, { json: { action: 'confirm' } }); toast('Статус подтверждён — оценка сохранена'); const y = window.scrollY; await route(); window.scrollTo(0, y); }
    else if (a === 'change') changeDialog(act.dataset.id);
    else if (a === 'child') { childId = +act.dataset.id; route(); }
    else if (a === 'reanalyse') modal(`<h2>Пересчитать анализ?</h2><p class="muted">Запись не распознаётся заново: по готовой расшифровке повторяется только анализ ответов с текущими настройками. Ваши подтверждения по этому уроку сбросятся.</p><div class="actions"><button class="btn" data-act="close">Отмена</button><button class="btn primary" data-act="reanalyse-yes" data-id="${act.dataset.id}">Пересчитать</button></div>`);
    else if (a === 'reanalyse-yes') { await api(`/lessons/${act.dataset.id}/reanalyse`, { method: 'POST' }); closeModal(); toast('Анализ запущен'); route(); }
    else if (a === 'save-settings') { await api('/admin/settings', { json: formValues() }); toast('Настройки сохранены'); route(); }
    else if (a === 'test-llm') { const out = $('#test-out'); out.innerHTML = '<span class="spin"></span> Проверяю...';
      try { const r = await api('/admin/test-llm', { json: formValues() }); out.innerHTML = `<span class="t-green">Модель ${e(r.model)} ответила за ${r.seconds} с: «${e(r.answer)}»</span>`; }
      catch (err) { out.innerHTML = `<span class="t-red">${e(err.message)}</span>`; } }
    else if (a === 'load-models') { const r = await api('/admin/models', { json: formValues() }); $('#models-list').innerHTML = r.models.map((m) => `<option value="${e(m)}">`).join(''); toast(`Моделей найдено: ${r.models.length}. Начните вводить название`); }
    else if (a === 'view') { reportView = act.dataset.view; const y = window.scrollY; await route(); window.scrollTo(0, y); }
    else if (a === 'swap') modal(`<h2>Поменять роли местами?</h2><p class="muted">Говорящий, которого система сочла преподавателем, станет учеником, и наоборот. Анализ ответов будет пересчитан, ваши подтверждения по этому уроку сбросятся.</p><div class="actions"><button class="btn" data-act="close">Отмена</button><button class="btn primary" data-act="swap-yes" data-id="${act.dataset.id}">Поменять и пересчитать</button></div>`);
    else if (a === 'swap-yes') { act.disabled = true; await api(`/lessons/${act.dataset.id}/swap-roles`, { method: 'POST' }); closeModal(); toast('Роли поменяны, анализ пересчитан'); route(); }
  } catch (err) { toast(err.message); }
});

window.addEventListener('hashchange', route);
route();
