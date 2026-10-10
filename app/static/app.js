"use strict";
// 서버가 준 데이터는 항상 textContent로만 화면에 넣는다. HTML 문자열로 조립하지 않는다.

const list = document.getElementById("list");
const emptyText = document.getElementById("empty");
const errorBox = document.getElementById("error");
const summary = document.getElementById("summary");
const clearButton = document.getElementById("clear");
const addForm = document.getElementById("add-form");
const filters = document.getElementById("filters");

let todos = [];
let filter = "all";
let editingId = null;

async function request(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail) && data.detail[0] && data.detail[0].msg) message = data.detail[0].msg.replace(/^Value error, /, "");
    } catch { /* 본문이 JSON이 아니면 기본 문구를 쓴다 */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function showError(message) {
  errorBox.textContent = message || "";
  errorBox.hidden = !message;
}

async function run(action) {
  try {
    showError("");
    await action();
    await load();
  } catch (error) {
    showError(error.message);
  }
}

async function load() {
  todos = await request("GET", "/api/todos");
  render();
}

function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (name === "class") node.className = value;
    else if (name === "text") node.textContent = value;
    else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (value !== false && value !== null && value !== undefined) node.setAttribute(name, value === true ? "" : value);
  }
  node.append(...children);
  return node;
}

function localToday() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

// 마감일(YYYY-MM-DD)을 사용자의 달력 날짜로 해석해 "오늘", "내일", "3일 지남"처럼 보여 준다.
function describeDue(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  const days = Math.round((new Date(year, month - 1, day) - localToday()) / 86400000);
  if (days === 0) return { text: "오늘까지", kind: "today" };
  if (days === 1) return { text: "내일까지", kind: "" };
  if (days > 1) return { text: `${month}월 ${day}일까지`, kind: "" };
  return { text: days === -1 ? "어제 마감 (지남)" : `${-days}일 지남`, kind: "overdue" };
}

function visible() {
  return todos.filter(todo => filter === "all" || (filter === "done") === todo.done);
}

function renderItem(todo) {
  if (todo.id === editingId) return renderEditor(todo);
  const checkbox = el("input", { type: "checkbox", "aria-label": `${todo.title} 완료`, checked: todo.done,
    onchange: event => run(() => request("PATCH", `/api/todos/${todo.id}`, { done: event.target.checked })) });
  const title = el("div", { class: "title", text: todo.title, ondblclick: () => startEdit(todo.id) });
  const text = el("div", { class: "text" }, title);
  if (todo.due_on) {
    const due = describeDue(todo.due_on);
    text.append(el("div", { class: `meta ${todo.done ? "" : due.kind}`, text: due.text }));
  }
  const actions = el("div", { class: "actions" },
    el("button", { type: "button", "aria-label": `${todo.title} 수정`, title: "수정", text: "✎", onclick: () => startEdit(todo.id) }),
    el("button", { type: "button", class: "remove", "aria-label": `${todo.title} 삭제`, title: "삭제", text: "✕",
      onclick: () => run(() => request("DELETE", `/api/todos/${todo.id}`)) }));
  return el("li", { class: `todo${todo.done ? " done" : ""}` }, checkbox, text, actions);
}

function renderEditor(todo) {
  const title = el("input", { type: "text", maxlength: 200, value: todo.title, "aria-label": "제목 수정", required: true });
  const due = el("input", { type: "date", value: todo.due_on || "", "aria-label": "마감일 수정" });
  const save = () => {
    const value = title.value.trim();
    if (!value) return showError("제목을 입력해 주세요.");
    editingId = null;
    run(() => request("PATCH", `/api/todos/${todo.id}`, { title: value, due_on: due.value || null }));
  };
  const cancel = () => { editingId = null; render(); };
  title.addEventListener("keydown", event => { if (event.key === "Enter") save(); if (event.key === "Escape") cancel(); });
  due.addEventListener("keydown", event => { if (event.key === "Enter") save(); if (event.key === "Escape") cancel(); });
  const row = el("div", { class: "row" }, due,
    el("button", { type: "button", text: "취소", onclick: cancel }),
    el("button", { type: "button", class: "primary", text: "저장", onclick: save }));
  setTimeout(() => title.focus(), 0);
  return el("li", { class: "todo" }, el("span"), el("div", { class: "edit" }, title, row));
}

function startEdit(id) {
  editingId = id;
  render();
}

function render() {
  const active = todos.filter(todo => !todo.done).length;
  const done = todos.length - active;
  document.getElementById("count-all").textContent = todos.length;
  document.getElementById("count-active").textContent = active;
  document.getElementById("count-done").textContent = done;
  summary.textContent = todos.length === 0 ? "" : active === 0 ? "모두 끝냈어요 🎉" : `${active}개 남음`;
  clearButton.disabled = done === 0;
  for (const button of filters.querySelectorAll("button")) button.setAttribute("aria-pressed", String(button.dataset.filter === filter));

  const items = visible();
  list.replaceChildren(...items.map(renderItem));
  emptyText.hidden = items.length > 0;
  if (items.length === 0) {
    emptyText.textContent = todos.length === 0 ? "아직 할 일이 없습니다. 위에서 추가해 보세요."
      : filter === "active" ? "진행 중인 할 일이 없습니다." : "완료한 할 일이 없습니다.";
  }
}

addForm.addEventListener("submit", event => {
  event.preventDefault();
  const title = addForm.elements.title.value.trim();
  if (!title) return showError("제목을 입력해 주세요.");
  run(async () => {
    await request("POST", "/api/todos", { title, due_on: addForm.elements.due.value || null });
    addForm.reset();
    addForm.elements.title.focus();
  });
});

filters.addEventListener("click", event => {
  const button = event.target.closest("button[data-filter]");
  if (!button) return;
  filter = button.dataset.filter;
  render();
});

clearButton.addEventListener("click", () => run(() => request("DELETE", "/api/todos?status=done")));

load().catch(error => showError(error.message));
