const $ = selector => document.querySelector(selector);
const state = {auth: null, user: null, menu: [], cart: new Map(), session: null, checkoutKey: null};
const photos = [
  'https://images.unsplash.com/photo-1630383249896-424e482df921?w=600&h=400&fit=crop',
  'https://images.unsplash.com/photo-1563379926898-05f4575a45d8?w=600&h=400&fit=crop',
  'https://images.unsplash.com/photo-1589301760014-d929f3979dbc?w=600&h=400&fit=crop',
  'https://images.unsplash.com/photo-1626132647523-66f5bf380027?w=600&h=400&fit=crop',
  'https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=600&h=400&fit=crop',
  'https://images.unsplash.com/photo-1563379926898-05f4575a45d8?w=600&h=400&fit=crop',
  'https://images.unsplash.com/photo-1532550907401-a500c9a57435?w=600&h=400&fit=crop',
  'https://images.unsplash.com/photo-1512058564366-18510be2db19?w=600&h=400&fit=crop',
  'https://images.unsplash.com/photo-1570696516188-ade861b84a49?w=600&h=400&fit=crop',
  'https://images.unsplash.com/photo-1601050690597-df0568f70950?w=600&h=400&fit=crop'
];
const money = amount => `₹${Number(amount).toLocaleString('en-IN', {maximumFractionDigits: 2})}`;
const icons = () => window.lucide?.createIcons();
const element = (tag, className, text) => {const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node;};
function toast(message) {const node = $('#toast'); node.textContent = message; node.classList.add('show'); clearTimeout(toast.timer); toast.timer = setTimeout(() => node.classList.remove('show'), 4500);}
async function api(path, options = {}) {
  const headers = {...options.headers};
  if (state.auth) headers.Authorization = `Basic ${state.auth}`;
  if (options.body && !(options.body instanceof FormData)) {headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.body);}
  const response = await fetch(path, {...options, headers});
  if (!response.ok) {let message = 'Request failed'; try {message = (await response.json()).message || message;} catch (_) {} throw new Error(message);}
  return response.status === 204 ? null : response.json();
}
function requireLogin() {if (state.auth) return true; $('#login-dialog').showModal(); return false;}
function showView(name) {
  if ((name === 'orders' || name === 'chat' || name === 'admin') && !requireLogin()) return;
  if (name === 'admin' && state.user?.role !== 'admin') return;
  document.querySelectorAll('.view').forEach(view => view.hidden = view.id !== `view-${name}`);
  document.querySelectorAll('.nav').forEach(button => button.classList.toggle('active', button.dataset.view === name));
  if (name === 'orders') loadOrders();
  if (name === 'chat') loadSessions();
  if (name === 'admin') renderAdmin();
}
document.querySelectorAll('.nav').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
$('.brand').addEventListener('click', event => {event.preventDefault(); showView('menu');});
$('#login-button').addEventListener('click', () => $('#login-dialog').showModal());
document.querySelectorAll('.close-dialog').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    state.auth = btoa(`${$('#username').value}:${$('#password').value}`);
    state.user = await api('/api/me');
    $('#login-button span').textContent = state.user.username;
    $('.admin-only').hidden = state.user.role !== 'admin';
    $('#logout').hidden = false;
    $('#password').value = '';
    $('#login-dialog').close();
    toast(`Signed in as ${state.user.username}`);
  } catch (error) {state.auth = null; state.user = null; toast(error.message);}
});
$('#logout').addEventListener('click', () => {state.auth = null; state.user = null; state.session = null; state.cart.clear(); state.checkoutKey = null; $('#login-button span').textContent = 'Sign in'; $('.admin-only').hidden = true; $('#logout').hidden = true; $('#login-dialog').close(); renderBasket(); showView('menu');});

async function loadMenu() {
  try {
    const params = new URLSearchParams();
    if ($('#search').value.trim()) params.set('keyword', $('#search').value.trim());
    if ($('#category').value) params.set('category', $('#category').value);
    if ($('#vegetarian').checked) params.set('vegetarian', 'true');
    if ($('#max-price').value) params.set('max_price', $('#max-price').value);
    state.menu = await api(`/api/menu_items?${params}`);
    renderMenu();
    if (!$('#view-admin').hidden) renderAdmin();
  } catch (error) {toast(error.message);}
}
function renderMenu() {
  const list = $('#menu-list'); list.replaceChildren();
  $('#menu-count').textContent = `${state.menu.length} dishes`;
  if (!state.menu.length) list.append(element('p', 'empty', 'No dishes match your filters.'));
  state.menu.forEach(item => {
    const card = element('article', 'dish');
    const image = element('img', 'dish-image'); image.src = photos[(item.id - 1) % photos.length]; image.alt = item.title; image.loading = 'lazy'; image.onerror = () => {image.onerror = null; image.removeAttribute('src');};
    const body = element('div', 'dish-body'); const category = element('div', 'dish-category'); category.append(element('span', '', item.category));
    const marker = element('span', `veg-icon${item.vegetarian ? '' : ' nonveg'}`); marker.title = item.vegetarian ? 'Vegetarian' : 'Non-vegetarian'; category.append(marker);
    body.append(category, element('h3', '', item.title), element('p', '', item.description));
    const bottom = element('div', 'dish-bottom'); const price = element('strong', '', money(item.price)); price.append(element('small', '', item.capacity ? `${item.capacity} portions available` : 'Currently unavailable'));
    const add = element('button', 'add-button', '+ Add'); add.disabled = !item.capacity; add.addEventListener('click', () => changeCart(item, 1)); bottom.append(price, add); body.append(bottom); card.append(image, body); list.append(card);
  });
}
function changeCart(item, delta) {
  const existing = state.cart.get(item.id); const quantity = (existing?.quantity || 0) + delta;
  if (quantity > Math.min(10, item.capacity)) {toast('Maximum available quantity reached.'); return;}
  if (quantity <= 0) state.cart.delete(item.id); else state.cart.set(item.id, {item, quantity});
  state.checkoutKey = null; renderBasket();
}
function renderBasket() {
  const list = $('#basket-list'); list.replaceChildren(); let total = 0;
  if (!state.cart.size) list.append(element('p', 'empty', 'Your basket is empty. Add a dish to get started.'));
  for (const {item, quantity} of state.cart.values()) {
    total += Number(item.price) * quantity;
    const row = element('div', 'basket-item'); const info = element('div'); info.append(element('strong', '', item.title), element('small', '', money(item.price)));
    const controls = element('div', 'quantity'); const minus = element('button', '', '−'); minus.setAttribute('aria-label', `Remove one ${item.title}`); minus.addEventListener('click', () => changeCart(item, -1)); const plus = element('button', '', '+'); plus.setAttribute('aria-label', `Add one ${item.title}`); plus.addEventListener('click', () => changeCart(item, 1)); controls.append(minus, element('span', '', quantity), plus); row.append(info, controls); list.append(row);
  }
  $('#basket-total').textContent = money(total); $('#checkout').disabled = !state.cart.size;
}
$('#checkout').addEventListener('click', async () => {
  if (!requireLogin()) return;
  state.checkoutKey ||= crypto.randomUUID(); $('#checkout').disabled = true;
  try {const order = await api('/api/orders', {method:'POST', headers:{'Idempotency-Key': state.checkoutKey}, body:{lines:[...state.cart.values()].map(({item, quantity}) => ({item_id:item.id, quantity}))}}); state.cart.clear(); state.checkoutKey = null; renderBasket(); await loadMenu(); toast(`Order #${order.id} placed.`); showView('orders');} catch (error) {toast(error.message); renderBasket();}
});
let filterTimer; ['search','category','vegetarian','max-price'].forEach(id => $(`#${id}`).addEventListener('input', () => {clearTimeout(filterTimer); filterTimer = setTimeout(loadMenu, 250);}));

async function loadOrders() {
  const list = $('#orders-list'); list.replaceChildren();
  try {const orders = await api('/api/orders'); if (!orders.length) list.append(element('p', 'empty', 'You have not placed any orders yet.'));
    orders.forEach(order => {const row = element('article', 'order-row'); const info = element('div'); info.append(element('h3', '', `Order #${order.id}`), element('p', '', `${order.lines.reduce((sum, line) => sum + line.quantity, 0)} items · ${money(order.total)}`)); row.append(info, element('span', 'status', order.status)); if (order.status === 'CONFIRMED') {const cancel = element('button', 'outline-button', 'Cancel order'); cancel.addEventListener('click', async () => {if (!window.confirm(`Cancel order #${order.id}?`)) return; try {await api(`/api/orders/${order.id}/cancel`, {method:'POST'}); toast('Order cancelled.'); loadOrders(); loadMenu();} catch (error) {toast(error.message);}}); row.append(cancel);} list.append(row);});
  } catch (error) {toast(error.message);}
}

async function loadSessions() {
  try {const sessions = await api('/api/chat/sessions'); const list = $('#sessions'); list.replaceChildren(); sessions.forEach(session => {const button = element('button', `session-button${session.id === state.session ? ' active' : ''}`, session.title); button.addEventListener('click', () => selectSession(session.id)); list.append(button);}); if (!state.session && sessions.length) await selectSession(sessions[0].id);}
  catch (error) {toast(error.message);}
}
async function selectSession(id) {state.session = id; try {const messages = await api(`/api/chat/sessions/${id}/messages`); renderMessages(messages); await loadSessions();} catch (error) {toast(error.message);}}
$('#new-chat').addEventListener('click', async () => {try {const session = await api('/api/chat/sessions', {method:'POST'}); await selectSession(session.id);} catch (error) {toast(error.message);}});
function renderMessages(messages) {
  const list = $('#messages'); list.replaceChildren();
  if (!messages.length) {const empty = element('div', 'chat-empty'); empty.append(element('h2', '', 'What can I help you find?'), element('p', '', 'Ask about a dish, policy, or order.')); list.append(empty);}
  messages.forEach(message => {const node = element('div', `message ${message.role}`, message.content); if (message.citations?.length) {const sources = element('div', 'sources'); message.citations.forEach(citation => sources.append(element('span', 'source', `${citation.filename} · ${citation.location}`))); node.append(sources);}
    (message.pending_actions || []).forEach(action => {const box = element('div', 'action-box'); let description = action.action === 'prepare_order' ? action.details.items.map(item => `${item.quantity} × ${item.title} (${money(item.unit_price)} each)`).join(', ') : `Cancel order #${action.details.order_id} (${money(action.details.total)})`; box.append(element('strong', '', description)); if (!action.status || ['PENDING', 'PROCESSING'].includes(action.status)) {const buttons = element('div', 'action-buttons'); const yes = element('button', 'primary-button', action.status === 'PROCESSING' ? 'Retry confirmation' : 'Confirm'); const no = element('button', 'outline-button', 'Reject'); no.disabled = action.status === 'PROCESSING'; yes.addEventListener('click', () => actionResponse(action.pending_action_id, true)); no.addEventListener('click', () => actionResponse(action.pending_action_id, false)); buttons.append(yes, no); box.append(buttons);} else box.append(element('p', '', action.status)); node.append(box);}); list.append(node);}); list.scrollTop = list.scrollHeight;
}
async function actionResponse(id, confirm) {try {await api(`/api/chat/actions/${id}/confirm`, {method:'POST', body:{confirm}}); await selectSession(state.session); await loadMenu();} catch (error) {toast(error.message);}}
$('#chat-form').addEventListener('submit', async event => {event.preventDefault(); if (!requireLogin()) return; const input = $('#chat-input'); const text = input.value.trim(); if (!text) return; const button = $('#chat-form button'); button.disabled = true;
  try {if (!state.session) {const session = await api('/api/chat/sessions', {method:'POST'}); state.session = session.id;} input.value = ''; const messages = await api(`/api/chat/sessions/${state.session}/messages`); renderMessages([...messages, {role:'user', content:text}, {role:'assistant', content:'Thinking...'}]); await api(`/api/chat/sessions/${state.session}/messages`, {method:'POST', body:{message:text}}); await selectSession(state.session);} catch (error) {toast(error.message); if (state.session) await selectSession(state.session);} finally {button.disabled = false; input.focus();}});

async function renderAdmin() {
  try {const items = await api('/api/menu_items'); const list = $('#admin-items'); list.replaceChildren(); items.forEach(item => {const row = element('div', 'admin-row'); row.append(element('strong', '', item.title), element('small', '', `${money(item.price)} · ${item.capacity} left`)); const edit = element('button', 'icon-button'); edit.title = 'Edit item'; edit.setAttribute('aria-label', `Edit ${item.title}`); edit.innerHTML = '<i data-lucide="pencil"></i>'; edit.addEventListener('click', () => editItem(item)); const remove = element('button', 'icon-button'); remove.title = 'Disable item'; remove.setAttribute('aria-label', `Disable ${item.title}`); remove.innerHTML = '<i data-lucide="archive"></i>'; remove.addEventListener('click', async () => {if (!window.confirm(`Disable ${item.title}?`)) return; try {await api(`/api/menu_items/${item.id}`, {method:'DELETE'}); renderAdmin(); loadMenu();} catch (error) {toast(error.message);}}); row.append(edit, remove); list.append(row);}); icons();} catch (error) {toast(error.message);}
}
function editItem(item = null) {$('#item-form').reset(); $('#item-id').value = item?.id || ''; $('#item-form-title').textContent = item ? 'Edit item' : 'Add item'; if (item) {for (const key of ['title','category','description','price','capacity']) $(`#item-${key}`).value = item[key]; $('#item-vegetarian').checked = item.vegetarian;} $('#item-dialog').showModal();}
$('#new-item').addEventListener('click', () => editItem());
$('#item-form').addEventListener('submit', async event => {event.preventDefault(); const id = $('#item-id').value; const body = {title:$('#item-title').value, category:$('#item-category').value, description:$('#item-description').value, price:$('#item-price').value, capacity:Number($('#item-capacity').value), vegetarian:$('#item-vegetarian').checked}; try {await api(`/api/menu_items${id ? `/${id}` : ''}`, {method:id ? 'PUT' : 'POST', body}); $('#item-dialog').close(); toast('Menu updated.'); renderAdmin(); loadMenu();} catch (error) {toast(error.message);}});
$('#upload-form').addEventListener('submit', async event => {event.preventDefault(); const data = new FormData(); data.append('file', $('#document').files[0]); try {const result = await api('/api/documents', {method:'POST', body:data}); toast(`Indexed ${result.filename}.`); event.target.reset();} catch (error) {toast(error.message);}});
$('#status-form').addEventListener('submit', async event => {event.preventDefault(); try {await api(`/api/admin/orders/${$('#status-order-id').value}/status`, {method:'PATCH', body:{status:$('#status-value').value}}); toast('Order status updated.');} catch (error) {toast(error.message);}});
renderBasket(); loadMenu(); icons();