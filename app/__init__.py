"""CampusClaw Freebird Flask application."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from functools import wraps
from pathlib import Path

import click
from flask import (
    Flask,
    Response,
    abort,
    g,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_from_directory,
    stream_with_context,
    url_for,
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from .auth import JwtService, TokenValidationError
from .db import (
    close_db,
    get_db,
    get_user,
    get_user_by_username,
    initialize_database,
    is_member,
    is_token_revoked,
    revoke_token,
)
from .mcp_client import (
    HttpMcpClient,
    McpError,
    McpUnauthorized,
    SERVER_NAME_PATTERN,
    TOOL_REFERENCE_PATTERN,
    TokenCipher,
    normalize_base_url,
)
from .retrieval import (
    AIAnswerUnavailable,
    DEFAULT_CHUNK_STRATEGY,
    EMPTY_SEARCH_MESSAGE,
    VALID_STRATEGIES,
    DeterministicEmbedder,
    InMemoryChunkStore,
    InMemoryVectorStore,
    MySQLChunkStore,
    OpenAIChatClient,
    OpenAIEmbedder,
    QdrantVectorStore,
    RetrievalService,
)
from .tutoring import (
    MAX_AGENT_NAME_LENGTH,
    MAX_AGENT_PROMPT_LENGTH,
    MAX_AGENT_EVIDENCE,
    MAX_QUESTION_LENGTH,
    SkillValidationError,
    build_chat_messages,
    parse_skill_source,
    route_skill,
    sse_event,
    strip_reference_stream,
)


MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_MULTIPART_OVERHEAD = 1024 * 1024


LOGIN_TEMPLATE = """<!doctype html><title>登录</title><head><meta name=viewport content="width=device-width, initial-scale=1"><style>
:root { color-scheme: light; --blue-700:#075bb5; --blue-600:#0b72d0; --blue-100:#dceeff; --blue-50:#f4f9ff; --ink:#102a43; --muted:#52667a; --line:#c9def4; }
* { box-sizing:border-box; }
body { min-height:100vh; margin:0; padding:32px 16px; background:linear-gradient(145deg, #e8f3ff, #f8fbff 55%, #dceeff); color:var(--ink); font:16px/1.55 system-ui, -apple-system, "Microsoft YaHei", sans-serif; }
#app { width:min(100%, 1180px); min-height:240px; margin:0 auto; padding:32px; background:#fff; border:1px solid var(--line); border-radius:18px; box-shadow:0 16px 40px rgba(19, 83, 146, .13); }
h1 { margin:0 0 24px; color:var(--blue-700); text-align:center; font-size:clamp(1.55rem, 4vw, 2rem); }
h2 { margin:26px 0 12px; color:var(--blue-700); font-size:1.15rem; }
form { display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin:16px 0; padding:18px; background:var(--blue-50); border:1px solid var(--line); border-radius:12px; }
#login-form { width:min(100%, 390px); margin:0 auto; display:grid; }
label { display:grid; gap:6px; color:var(--muted); font-weight:600; }
input, select, textarea { min-width:0; border:1px solid #aac9e8; border-radius:8px; padding:9px 10px; color:var(--ink); background:#fff; font:inherit; }
input:focus, select:focus, textarea:focus { outline:3px solid rgba(11, 114, 208, .22); border-color:var(--blue-600); }
textarea { width:100%; min-height:120px; resize:vertical; }
button { border:0; border-radius:8px; padding:9px 14px; background:var(--blue-600); color:#fff; font:inherit; font-weight:700; cursor:pointer; transition:background .15s ease, transform .15s ease; }
button:hover { background:var(--blue-700); transform:translateY(-1px); }
button:focus-visible { outline:3px solid rgba(11, 114, 208, .3); outline-offset:2px; }
[hidden] { display:none !important; }
.workspace-header { display:flex; flex-wrap:wrap; align-items:center; justify-content:flex-end; gap:12px; margin-bottom:18px; }
.workspace-header label { display:flex; align-items:center; gap:8px; }
.workspace-header p { margin:0; }
.workspace-shell { display:grid; grid-template-columns:210px minmax(0, 1fr); gap:24px; align-items:start; }
.feature-navigation { position:sticky; top:16px; display:flex; flex-direction:column; gap:8px; padding:16px; background:var(--blue-50); border:1px solid var(--line); border-radius:12px; }
.feature-navigation strong { margin-bottom:4px; color:var(--blue-700); }
.feature-navigation button { width:100%; background:#fff; color:var(--blue-700); border:1px solid var(--line); text-align:left; }
.feature-navigation button[aria-pressed="true"] { background:var(--blue-600); color:#fff; border-color:var(--blue-600); }
.feature-content { min-width:0; }
.feature-panel > h2 { margin-top:0; }
#message, #error { min-height:1.5em; color:#a12a2a; font-weight:600; text-align:center; }
#message:empty { display:none; }
ul { margin:12px 0; padding:0; list-style:none; }
li { margin:10px 0; padding:14px; background:#fff; border:1px solid var(--line); border-radius:10px; }
li button { text-align:left; }
pre { overflow:auto; margin:10px 0 0; padding:12px; white-space:pre-wrap; background:var(--blue-50); border-radius:8px; color:#24415d; font:14px/1.5 ui-monospace, Consolas, monospace; }
#detail, #answer { margin-top:18px; padding:4px 18px 18px; background:#fff; border-left:4px solid var(--blue-600); border-radius:0 10px 10px 0; }
#answer:empty, #detail:empty { display:none; }
#question-form label:first-child { flex:1; }
.answer-text { white-space:pre-wrap; }
.chat-log { display:grid; gap:12px; margin:16px 0; }
.chat-message { padding:12px 14px; border-radius:12px; white-space:pre-wrap; }
.chat-message.user { margin-left:12%; background:var(--blue-100); }
.chat-message.assistant { margin-right:12%; background:#f6f8fb; border:1px solid var(--line); }
.chat-meta { color:var(--muted); font-size:.9rem; }
.mcp-status { color:var(--muted); font-size:.9rem; }
.stack { display:grid; gap:10px; width:100%; }
.binding-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; width:100%; }
.binding-grid select { min-height:110px; }
.skill-fieldset { width:100%; min-width:0; margin:0; padding:0; border:0; }
.skill-fieldset legend { margin-bottom:8px; color:var(--muted); font-weight:700; }
.skill-picker { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:9px; width:100%; margin:8px 0; }
.skill-option { display:flex; align-items:flex-start; gap:10px; min-width:0; padding:11px; background:#fff; border:1px solid var(--line); border-radius:10px; cursor:pointer; font-weight:400; }
.skill-option:hover { border-color:var(--blue-600); background:#fafdff; }
.skill-option:has(input:checked) { border-color:var(--blue-600); background:var(--blue-100); }
.skill-option input { flex:0 0 auto; width:18px; height:18px; margin:3px 0 0; padding:0; }
.skill-option span { min-width:0; }
.skill-option strong, .skill-option small { display:block; }
.skill-option strong { color:var(--ink); }
.skill-option small, .skill-help { color:var(--muted); font-weight:400; }
.skill-actions { display:flex; gap:8px; margin-bottom:4px; }
.skill-actions button { padding:6px 10px; background:#fff; color:var(--blue-700); border:1px solid var(--line); }
.empty-skill { margin:0; padding:12px; color:var(--muted); background:#fff; border:1px dashed var(--line); border-radius:10px; }
.agent-setup { display:grid; gap:14px; margin:16px 0; padding:18px; background:var(--blue-50); border:1px solid var(--line); border-radius:12px; }
button:disabled { opacity:.65; cursor:wait; transform:none; }
@media (max-width:760px) { body { padding:16px 10px; } #app { padding:22px 16px; } .workspace-shell { grid-template-columns:1fr; } .feature-navigation { position:static; flex-direction:row; flex-wrap:wrap; } .feature-navigation strong { width:100%; } .feature-navigation button { width:auto; } .skill-picker { grid-template-columns:1fr; } form { align-items:stretch; } form > * { width:100%; } button { width:auto; } }
</style></head><body><main id=app><h1>CampusClaw Freebird 登录</h1>
<p id=error role=alert></p><form id=login-form><label>账号 <input name=username required></label><label>密码 <input type=password name=password required></label><button>登录</button></form></main>
<script>
let accessToken = null;
const app = document.querySelector('#app');
function node(tag, text) { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; return element; }
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {}); headers.set('Authorization', 'Bearer ' + accessToken);
  const response = await fetch(path, {...options, headers});
  if (response.status === 401) { accessToken = null; window.location.replace('/login'); throw new Error('authentication_required'); }
  return response;
}
function download(path, filename) {
  api(path).then(response => { if (!response.ok) throw new Error('download_failed'); return response.blob(); }).then(blob => {
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = filename; link.click(); URL.revokeObjectURL(link.href);
  }).catch(error => setMessage(error.message));
}
function setMessage(message) { document.querySelector('#message').textContent = message || ''; }
function switchFeature(featureId) {
  for (const panel of document.querySelectorAll('.feature-panel')) panel.hidden = panel.id !== featureId;
  for (const button of document.querySelectorAll('.feature-navigation button')) button.setAttribute('aria-pressed', String(button.getAttribute('aria-controls') === featureId));
  setMessage('');
}
function detail(materialId) {
  api('/api/materials/' + materialId).then(response => response.json()).then(material => {
    const panel = document.querySelector('#detail'); panel.replaceChildren(node('h2', material.filename));
    const button = node('button', '下载原文件'); button.onclick = () => download(material.download_url, material.filename); panel.append(button, node('pre', material.content_text));
    switchFeature('feature-materials'); panel.scrollIntoView({behavior:'smooth', block:'start'});
  }).catch(error => setMessage(error.message));
}
function listMaterials() {
  const classId = document.querySelector('#class-id').value; if (!classId) return;
  api('/api/classes/' + classId + '/materials').then(response => response.json()).then(body => {
    const list = document.querySelector('#materials'); list.replaceChildren();
    if (!body.materials.length) list.append(node('li', '暂无材料'));
    for (const material of body.materials) {
      const item = node('li'); const open = node('button', material.title); open.onclick = () => detail(material.material_id); item.append(open);
      const get = node('button', '下载'); get.onclick = () => download('/api/materials/' + material.material_id + '/download', material.filename); item.append(' ', get);
      if (window.currentUser.role === 'teacher') { const rebuild = node('button', '重建索引'); rebuild.onclick = async () => { const response = await api('/api/materials/' + material.material_id + '/reindex', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}); setMessage(response.ok ? '索引重建成功' : '索引重建失败'); }; const remove = node('button', '删除'); remove.onclick = async () => { const response = await api('/api/materials/' + material.material_id + '/delete', {method:'POST'}); if (response.ok) { listMaterials(); refreshTeacherBindings(); } else setMessage('删除失败'); }; item.append(' ', rebuild, ' ', remove); }
      list.append(item);
    }
  }).catch(error => setMessage(error.message));
}
function search() {
  const classId = document.querySelector('#class-id').value, query = document.querySelector('#query').value.trim(), mode = document.querySelector('#mode').value;
  if (!query) return; api('/api/classes/' + classId + '/search?query=' + encodeURIComponent(query) + '&mode=' + encodeURIComponent(mode)).then(response => response.json()).then(body => {
    const results = document.querySelector('#results'); results.replaceChildren();
    if (!body.hits.length) results.append(node('p', body.message));
    for (const hit of body.hits) { const result = node('li'); const open = node('button', hit.title + '：切片 ' + hit.chunk_number + '，区间 [' + hit.char_range.start + ', ' + hit.char_range.end + ')'); open.onclick = () => detail(hit.material_url.split('/').pop()); result.append(open, node('pre', hit.excerpt)); results.append(result); }
  }).catch(error => setMessage(error.message));
}
async function askQuestion() {
  const classId = document.querySelector('#class-id').value, question = document.querySelector('#question').value.trim();
  const answerMode = document.querySelector('#answer-mode').value, submit = document.querySelector('#question-submit');
  if (!question || submit.disabled) return;
  submit.disabled = true; submit.textContent = '正在回答…'; setMessage('');
  const panel = document.querySelector('#answer'); panel.replaceChildren(node('p', '正在查找资料并回答…')); panel.setAttribute('aria-busy', 'true');
  try {
    const endpoint = answerMode === 'ai' ? '/ai-questions' : '/questions';
    const response = await api('/api/classes/' + classId + endpoint, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question})});
    if (!response.ok) throw new Error(response.status === 502 ? 'AI 暂时无法回答，请稍后重试或选择原文摘录。' : '问答失败，请重试。');
    const body = await response.json();
    if (document.querySelector('#class-id').value !== classId) return;
    const answer = node('p', body.answer); answer.className = 'answer-text'; panel.replaceChildren(node('h2', answerMode === 'ai' ? 'AI 回答' : '原文摘录'), answer);
    if (body.keywords) panel.append(node('p', body.keywords.length ? '关键词：' + body.keywords.join('、') : '未提取到可检索关键词'));
    const citations = node('ul');
    for (const citation of body.citations) { const item = node('li'); const open = node('button', citation.title + '：切片 ' + citation.chunk_number + '，区间 [' + citation.char_range.start + ', ' + citation.char_range.end + ')'); open.onclick = () => detail(citation.material_url.split('/').pop()); item.append(open, node('pre', citation.excerpt)); citations.append(item); }
    panel.append(citations);
  } catch (error) { panel.replaceChildren(); setMessage(error.message); }
  finally { submit.disabled = false; submit.textContent = '提问'; panel.setAttribute('aria-busy', 'false'); }
}
let activeConversationId = null;
let activeConversationAgentId = null;
let availableAgents = [];
async function jsonApi(path, options = {}) {
  const response = await api(path, options); const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || body.error || 'request_failed'); return body;
}
function citationList(citations) {
  const list = node('ul');
  for (const citation of citations || []) {
    const item = node('li'); const open = node('button', citation.title + '：切片 ' + citation.chunk_number);
    open.type = 'button'; open.onclick = () => detail(citation.material_url.split('/').pop());
    item.append(open, node('pre', citation.excerpt)); list.append(item);
  }
  return list;
}
async function loadAgentOptions() {
  const classId = document.querySelector('#class-id').value;
  const body = await jsonApi('/api/classes/' + classId + '/agents');
  availableAgents = body.agents;
  const chooser = document.querySelector('#conversation-agent');
  if (chooser) {
    chooser.replaceChildren();
    for (const agent of body.agents) { const option = node('option', agent.name); option.value = agent.id; chooser.append(option); }
    chooser.onchange = async () => {
      activeConversationId = null; activeConversationAgentId = null;
      const log = document.querySelector('#chat-log'); if (log) log.replaceChildren();
      await loadConversationSkillOptions('conversation-skills', Number(chooser.value));
      setMessage('已切换智能体，选择技能后可直接提问');
    };
    await loadConversationSkillOptions('conversation-skills', Number(chooser.value));
  }
  const list = document.querySelector('#agent-list');
  if (list) { list.replaceChildren(); for (const agent of body.agents) { const item = node('li', agent.name + (agent.enabled ? '（已启用）' : '（已停用）')); if (window.currentUser.role === 'teacher') { const toggle = node('button', agent.enabled ? '停用' : '启用'); toggle.type = 'button'; toggle.onclick = async () => { try { await jsonApi('/api/classes/' + classId + '/agents/' + agent.id, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:!agent.enabled})}); await loadAgentOptions(); } catch (error) { setMessage(error.message); } }; item.append(' ', toggle); } list.append(item); } }
  return body.agents;
}
async function loadConversationSkillOptions(selectId, agentId, selectedIds = null, allowedSkillIds = null) {
  const picker = document.querySelector('#' + selectId); if (!picker) return;
  const agent = availableAgents.find(item => item.id === Number(agentId));
  const body = await jsonApi('/api/classes/' + document.querySelector('#class-id').value + '/skills');
  const permittedIds = allowedSkillIds === null ? (agent ? agent.skill_ids : []) : allowedSkillIds;
  const allowed = body.skills.filter(skill => skill.enabled && permittedIds.includes(skill.id));
  picker.replaceChildren();
  for (const skill of allowed) {
    const option = node('label'); option.className = 'skill-option';
    const checkbox = node('input'); checkbox.type = 'checkbox'; checkbox.value = skill.id; checkbox.checked = selectedIds === null ? true : selectedIds.includes(skill.id);
    const copy = node('span'); copy.append(node('strong', skill.name), node('small', skill.description));
    option.append(checkbox, copy); picker.append(option);
  }
  if (!allowed.length) { const empty = node('p', '该智能体暂无可加载技能，可直接使用基础能力。'); empty.className = 'empty-skill'; picker.append(empty); }
}
function selectedSkillIds(pickerId) { return Array.from(document.querySelectorAll('#' + pickerId + ' input[type=checkbox]:checked')).map(input => Number(input.value)); }
function setSkillSelection(pickerId, checked) { for (const input of document.querySelectorAll('#' + pickerId + ' input[type=checkbox]')) input.checked = checked; }
async function loadSkills() {
  const list = document.querySelector('#skill-list'); if (!list) return [];
  const body = await jsonApi('/api/classes/' + document.querySelector('#class-id').value + '/skills');
  list.replaceChildren(); for (const skill of body.skills) { const item = node('li', skill.name + (skill.enabled ? '（已启用）' : '（已停用）') + '：' + skill.trigger_text); if (window.currentUser.role === 'teacher') { const remove = node('button', '删除'); remove.type = 'button'; remove.onclick = async () => { try { await jsonApi('/api/classes/' + document.querySelector('#class-id').value + '/skills/' + skill.id, {method:'DELETE'}); await loadSkills(); await loadAgentOptions(); await refreshTeacherBindings(); } catch (error) { setMessage(error.message); } }; item.append(' ', remove); } list.append(item); }
  return body.skills;
}
async function loadMcpServers() {
  const list = document.querySelector('#mcp-server-list'); if (!list) return;
  try {
    const body = await jsonApi('/api/classes/' + document.querySelector('#class-id').value + '/mcp-servers');
    list.replaceChildren();
    if (!body.servers.length) list.append(node('li', '尚未登记 MCP 服务器'));
    for (const server of body.servers) {
      const item = node('li');
      item.append(node('strong', server.name), node('p', server.base_url + ' · ' + server.status));
      if (server.last_error) item.append(node('p', '连接错误：' + server.last_error));
      const tools = node('p', server.tools.length ? '已发现工具：' + server.tools.map(tool => tool.name).join('、') : '尚未缓存工具'); tools.className = 'mcp-status'; item.append(tools);
      const action = node('button', server.status === 'connected' ? '重新连接' : '连接'); action.type = 'button';
      action.onclick = async () => { try { await jsonApi('/api/classes/' + server.class_id + '/mcp-servers/' + server.id + '/connect', {method:'POST'}); await loadMcpServers(); setMessage('MCP 连接与工具发现成功'); } catch (error) { await loadMcpServers(); setMessage(error.message); } };
      const disconnect = node('button', '断开'); disconnect.type = 'button'; disconnect.disabled = server.status === 'disconnected';
      disconnect.onclick = async () => { try { await jsonApi('/api/classes/' + server.class_id + '/mcp-servers/' + server.id + '/disconnect', {method:'POST'}); await loadMcpServers(); setMessage('MCP 已断开，工具缓存已清空'); } catch (error) { setMessage(error.message); } };
      item.append(action, ' ', disconnect); list.append(item);
    }
  } catch (error) { setMessage(error.message); }
}
async function loadMcpAudit() {
  const list = document.querySelector('#mcp-audit-list'); if (!list) return;
  try {
    const body = await jsonApi('/api/classes/' + document.querySelector('#class-id').value + '/mcp-audit');
    list.replaceChildren();
    if (!body.audit.length) list.append(node('li', '暂无 MCP 调用记录'));
    for (const record of body.audit) list.append(node('li', record.created_at + ' · ' + record.display_name + ' · ' + record.tool_ref + ' · ' + record.status));
  } catch (error) { setMessage(error.message); }
}
async function refreshTeacherBindings() {
  const skillSelect = document.querySelector('#agent-skills'), materialSelect = document.querySelector('#agent-materials');
  if (!skillSelect || !materialSelect) return;
  const classId = document.querySelector('#class-id').value;
  const [skills, materials] = await Promise.all([
    jsonApi('/api/classes/' + classId + '/skills'),
    jsonApi('/api/classes/' + classId + '/materials')
  ]);
  skillSelect.replaceChildren(); materialSelect.replaceChildren();
  for (const skill of skills.skills) { const option = node('option', skill.name); option.value = skill.id; skillSelect.append(option); }
  for (const material of materials.materials) { const option = node('option', material.title); option.value = material.material_id; materialSelect.append(option); }
}
async function loadConversations() {
  const classId = document.querySelector('#class-id').value;
  const body = await jsonApi('/api/classes/' + classId + '/conversations');
  const list = document.querySelector('#conversation-list'); if (!list) return;
  list.replaceChildren();
  for (const conversation of body.conversations) {
    const item = node('li'); const open = node('button', conversation.title); open.type = 'button'; open.onclick = () => openConversation(conversation.id); item.append(open); list.append(item);
  }
}
async function openConversation(conversationId) {
  const body = await jsonApi('/api/conversations/' + conversationId); activeConversationId = conversationId; activeConversationAgentId = body.conversation.agent_id;
  const agentChooser = document.querySelector('#conversation-agent'); if (agentChooser) agentChooser.value = String(body.conversation.agent_id);
  await loadConversationSkillOptions('conversation-skills', body.conversation.agent_id, body.conversation.skill_ids, body.conversation.available_skill_ids);
  const log = document.querySelector('#chat-log'); log.replaceChildren();
  for (const message of body.conversation.messages) {
    const wrapper = node('article'); wrapper.className = 'chat-message ' + message.role;
    wrapper.append(node('div', message.content));
    if (message.skill_name) { const meta = node('p', '技能：' + message.skill_name); meta.className = 'chat-meta'; wrapper.append(meta); }
    if (message.citations && message.citations.length) wrapper.append(citationList(message.citations));
    log.append(wrapper);
  }
}
async function ensureConversationForSelection() {
  const agentId = Number(document.querySelector('#conversation-agent').value);
  if (!agentId) throw new Error('当前班级没有可用智能体');
  const skillIds = selectedSkillIds('conversation-skills');
  if (!activeConversationId || activeConversationAgentId !== agentId) {
    const body = await jsonApi('/api/classes/' + document.querySelector('#class-id').value + '/conversations', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({agent_id:agentId, skill_ids:skillIds})
    });
    activeConversationId = body.conversation.id; activeConversationAgentId = agentId;
    await loadConversations();
  } else {
    await jsonApi('/api/conversations/' + activeConversationId + '/skills', {
      method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({skill_ids:skillIds})
    });
  }
}
function decodeSseFrames(buffer, onEvent) {
  const frames = buffer.split(/\\r?\\n\\r?\\n/); const rest = frames.pop();
  for (const frame of frames) {
    let event = 'message', data = '';
    for (const line of frame.split(/\\r?\\n/)) { if (line.startsWith('event:')) event = line.slice(6).trim(); if (line.startsWith('data:')) data += line.slice(5).trim(); }
    if (data) onEvent(event, JSON.parse(data));
  }
  return rest;
}
async function streamConversation(question) {
  if (!activeConversationId) throw new Error('请选择智能体和技能后再提问');
  const log = document.querySelector('#chat-log');
  const mine = node('article'); mine.className = 'chat-message user'; mine.textContent = question; log.append(mine);
  const assistant = node('article'); assistant.className = 'chat-message assistant'; const text = node('div', ''); assistant.append(text); log.append(assistant);
  const response = await api('/api/conversations/' + activeConversationId + '/messages', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question})});
  if (!response.ok || !response.body) { const body = await response.json().catch(() => ({})); throw new Error(body.error || '提问失败'); }
  const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
  const handle = (event, data) => {
    if (event === 'meta') { if (data.skill) { const meta = node('p', '技能：' + data.skill.name); meta.className = 'chat-meta'; assistant.append(meta); } if (data.tool_calls && data.tool_calls.length) { const tools = node('p', '工具：' + data.tool_calls.map(call => call.ref + '（' + call.status + '）').join('、')); tools.className = 'chat-meta'; assistant.append(tools); } if (data.citations.length) assistant.append(citationList(data.citations)); }
    if (event === 'delta') text.textContent += data.text;
    if (event === 'error') setMessage(data.message);
  };
  while (true) { const part = await reader.read(); buffer += decoder.decode(part.value || new Uint8Array(), {stream:!part.done}); buffer = decodeSseFrames(buffer, handle); if (part.done) break; }
  loadConversations();
}
async function renderWorkspace() {
  const response = await api('/api/me'); window.currentUser = await response.json();
  app.replaceChildren();
  const user = node('p', window.currentUser.display_name + '（' + (window.currentUser.role === 'teacher' ? '教师' : '学生') + '）'); const logout = node('button', '退出');
  logout.onclick = async () => { await api('/api/auth/logout', {method:'POST'}); accessToken = null; window.location.replace('/login'); }; const header = node('div'); header.className = 'workspace-header'; header.append(user, logout); app.append(header);
  const chooser = node('select'); chooser.id = 'class-id'; for (const classInfo of window.currentUser.classes) { const option = node('option', classInfo.name); option.value = classInfo.id; chooser.append(option); }
  chooser.onchange = () => {
    activeConversationId = null;
    activeConversationAgentId = null;
    availableAgents = [];
    for (const id of ['detail', 'answer', 'results', 'chat-log']) { const target = document.getElementById(id); if (target) target.replaceChildren(); }
    listMaterials(); loadAgentOptions(); loadConversations(); loadSkills(); refreshTeacherBindings(); loadMcpServers(); loadMcpAudit(); setMessage('');
  };
  const classLabel = node('label', '班级'); classLabel.append(chooser); header.replaceChildren(user, classLabel, logout); app.append(node('h1', '班级智能学习空间'));
  const message = node('p'); message.id = 'message'; message.setAttribute('role', 'status'); app.append(message);
  const shell = node('div'); shell.className = 'workspace-shell'; const navigation = node('nav'); navigation.className = 'feature-navigation'; navigation.setAttribute('aria-label', '主要功能'); navigation.append(node('strong', '主要功能')); const featureContent = node('div'); featureContent.className = 'feature-content'; shell.append(navigation, featureContent); app.append(shell);
  function addFeature(id, title) {
    const panel = node('section'); panel.id = id; panel.className = 'feature-panel'; panel.hidden = true;
    const heading = node('h2', title); heading.id = id + '-heading'; panel.setAttribute('aria-labelledby', heading.id); panel.append(heading);
    const button = node('button', title); button.type = 'button'; button.setAttribute('aria-controls', id); button.setAttribute('aria-pressed', 'false'); button.onclick = () => switchFeature(id); navigation.append(button); featureContent.append(panel); return panel;
  }
  const materialsPanel = addFeature('feature-materials', '材料列表'); const materials = node('ul'); materials.id = 'materials'; const detailPanel = node('section'); detailPanel.id = 'detail'; materialsPanel.append(materials, detailPanel);
  if (window.currentUser.role === 'teacher') { const uploadPanel = addFeature('feature-upload', '上传材料'); const upload = node('form'); upload.innerHTML = '<input type=file name=file accept=".txt,.md" required><select name=chunk_strategy><option value=semantic>默认：按结构</option><option value=window>固定窗口</option><option value=line>按换行</option><option value=blank_line>按空行</option><option value=sentence>按句号</option><option value=markdown_heading>按标题</option></select><button>上传</button>'; upload.onsubmit = async event => { event.preventDefault(); const response = await api('/api/classes/' + chooser.value + '/materials', {method:'POST', body:new FormData(upload)}); if (response.ok) { upload.reset(); listMaterials(); refreshTeacherBindings(); switchFeature('feature-materials'); setMessage('上传成功'); } else setMessage('上传失败'); }; uploadPanel.append(upload); }
  const tutorPanel = addFeature('feature-tutor', '学习助手');
  const sessionTools = node('section'); sessionTools.className = 'agent-setup'; sessionTools.innerHTML = '<label>选择智能体<select id=conversation-agent required></select></label><fieldset class=skill-fieldset><legend>选择提问时加载的技能</legend><div class=skill-actions><button id=conversation-skills-all type=button>全选</button><button id=conversation-skills-none type=button>清空</button></div><div id=conversation-skills class=skill-picker aria-describedby=conversation-skills-help></div><small id=conversation-skills-help class=skill-help>只显示教师为该智能体开放且当前已启用的技能；选好后直接在下方提问，首次提问会自动建立会话。</small></fieldset>';
  sessionTools.querySelector('#conversation-skills-all').onclick = () => setSkillSelection('conversation-skills', true); sessionTools.querySelector('#conversation-skills-none').onclick = () => setSkillSelection('conversation-skills', false);
  const conversations = node('ul'); conversations.id = 'conversation-list'; const chatLog = node('section'); chatLog.id = 'chat-log'; chatLog.className = 'chat-log'; chatLog.setAttribute('aria-live', 'polite');
  const chatForm = node('form'); chatForm.innerHTML = '<label>直接提问<input id=conversation-question required minlength=2 maxlength=500 placeholder=选好智能体和技能后直接提问></label><button>发送</button>';
  chatForm.onsubmit = async event => { event.preventDefault(); const input = document.querySelector('#conversation-question'), submit = event.currentTarget.querySelector('button'); if (!input.value.trim() || submit.disabled) return; submit.disabled = true; try { await ensureConversationForSelection(); await streamConversation(input.value.trim()); input.value = ''; } catch (error) { setMessage(error.message); } finally { submit.disabled = false; } };
  tutorPanel.append(sessionTools, chatForm, chatLog, node('h2', '我的会话'), conversations);
  if (window.currentUser.role === 'teacher') {
    const skillPanel = addFeature('feature-skills', '技能管理'); const skillForm = node('form'); skillForm.className = 'stack';
    skillForm.innerHTML = '<label>技能文件<textarea id=skill-source required placeholder="名称：数学解题引导&#10;适用条件：方程,去括号&#10;资料：数学&#10;工具：knowledge_search,formula_hint@campus-tools&#10;启用：是&#10;&#10;这里填写引导规程"></textarea></label><button>创建技能</button>';
    skillForm.onsubmit = async event => { event.preventDefault(); try { await jsonApi('/api/classes/' + chooser.value + '/skills', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({source_text:document.querySelector('#skill-source').value})}); event.currentTarget.reset(); await loadSkills(); await refreshTeacherBindings(); setMessage('技能创建成功'); } catch (error) { setMessage(error.message); } };
    const skillList = node('ul'); skillList.id = 'skill-list'; skillPanel.append(skillForm, skillList);
    const agentPanel = addFeature('feature-agents', '智能体管理'); const agentForm = node('form'); agentForm.className = 'stack';
    agentForm.innerHTML = '<label>名称<input id=agent-name required maxlength=64></label><label>角色提示词<textarea id=agent-prompt maxlength=2000 placeholder="留空则使用默认学习助手角色"></textarea></label><div class=binding-grid><label>绑定技能<select id=agent-skills multiple></select></label><label>绑定材料<select id=agent-materials multiple></select></label></div><label><input id=agent-enabled type=checkbox checked>启用</label><button>创建智能体</button>';
    agentForm.onsubmit = async event => { event.preventDefault(); const selected = id => Array.from(document.querySelector(id).selectedOptions).map(option => Number(option.value)); try { await jsonApi('/api/classes/' + chooser.value + '/agents', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:document.querySelector('#agent-name').value, prompt:document.querySelector('#agent-prompt').value, enabled:document.querySelector('#agent-enabled').checked, skill_ids:selected('#agent-skills'), material_ids:selected('#agent-materials')})}); event.currentTarget.reset(); document.querySelector('#agent-enabled').checked = true; await loadAgentOptions(); setMessage('智能体创建成功'); } catch (error) { setMessage(error.message); } };
    const agentList = node('ul'); agentList.id = 'agent-list'; agentPanel.append(agentForm, agentList);
    const mcpPanel = addFeature('feature-mcp', 'MCP 工具'); const mcpForm = node('form'); mcpForm.className = 'stack';
    mcpForm.innerHTML = '<label>服务器名称<input id=mcp-name required pattern="[a-z][a-z0-9_-]{0,63}" value=campus-tools></label><label>Base URL<input id=mcp-base-url type=url required value="http://mcp-demo:8090"></label><label>Bearer 令牌<input id=mcp-token type=password required autocomplete=new-password></label><button>登记服务器</button>';
    mcpForm.onsubmit = async event => { event.preventDefault(); try { await jsonApi('/api/classes/' + chooser.value + '/mcp-servers', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:document.querySelector('#mcp-name').value, base_url:document.querySelector('#mcp-base-url').value, token:document.querySelector('#mcp-token').value})}); document.querySelector('#mcp-token').value = ''; await loadMcpServers(); setMessage('MCP 服务器已登记，请点击连接发现工具'); } catch (error) { setMessage(error.message); } };
    const mcpServers = node('ul'); mcpServers.id = 'mcp-server-list'; const auditHeading = node('h2', '工具调用审计'); const auditRefresh = node('button', '刷新审计'); auditRefresh.type = 'button'; auditRefresh.onclick = loadMcpAudit; const audit = node('ul'); audit.id = 'mcp-audit-list'; mcpPanel.append(mcpForm, mcpServers, auditHeading, auditRefresh, audit);
  }
  const questionPanel = addFeature('feature-question', '知识问答'); const questionForm = node('form'); questionForm.id = 'question-form'; questionForm.innerHTML = '<label>问题<input id=question required maxlength=500 placeholder=根据本班资料提问></label><label>回答方式<select id=answer-mode><option value=ai>AI 回答</option><option value=keyword>原文摘录</option></select></label><button id=question-submit>提问</button>'; questionForm.onsubmit = event => { event.preventDefault(); askQuestion(); }; const answerPanel = node('section'); answerPanel.id = 'answer'; answerPanel.setAttribute('aria-live', 'polite'); questionPanel.append(questionForm, answerPanel);
  const searchPanel = addFeature('feature-search', '检索材料'); const searchForm = node('form'); searchForm.innerHTML = '<input id=query required placeholder=输入问题><select id=mode><option value=keyword>keyword</option><option value=vector>vector</option><option value=hybrid selected>hybrid</option></select><button>检索</button>'; searchForm.onsubmit = event => { event.preventDefault(); search(); }; const results = node('ul'); results.id = 'results'; searchPanel.append(searchForm, results);
  switchFeature('feature-tutor'); listMaterials(); loadAgentOptions(); loadConversations(); loadSkills(); refreshTeacherBindings(); loadMcpServers(); loadMcpAudit();
}
document.querySelector('#login-form').addEventListener('submit', async event => {
  event.preventDefault(); const response = await fetch('/api/auth/login', {method: 'POST', body: new FormData(event.currentTarget)}); const body = await response.json();
  if (!response.ok) { document.querySelector('#error').textContent = '账号或密码错误'; return; } accessToken = body.access_token; window.history.replaceState({}, '', '/materials'); renderWorkspace();
});
</script></body>"""

MATERIAL_TEMPLATE = """<!doctype html><title>材料</title><h1>班级材料</h1>
<p>{{ user['display_name'] }}（{{ user['role'] }}）</p>
<p>请使用 Bearer Token 调用 <code>/api/auth/logout</code> 退出。</p>
<p><a href="{{ url_for('search_page') }}">检索材料</a></p>
{% if user['role'] == 'teacher' %}<form method=post action="{{ url_for('upload_page') }}" enctype=multipart/form-data>
<label>班级 <select name=class_id>{% for class in classes %}<option value="{{ class['id'] }}">{{ class['name'] }}</option>{% endfor %}</select></label>
<label>切分 <select name=chunk_strategy><option value=semantic>默认：按结构</option><option value=window>固定窗口</option><option value=line>按换行</option><option value=blank_line>按空行</option><option value=sentence>按句号</option><option value=markdown_heading>按 Markdown 标题</option></select></label>
<input type=file name=file required><button>上传</button></form>{% endif %}
<ul>{% for material in materials %}<li><a href="{{ url_for('material_page', material_id=material['material_id']) }}">{{ material['title'] }}</a>（{{ material['class_name'] }}） <a href="{{ url_for('download_material', material_id=material['material_id']) }}">下载</a>{% if user['role'] == 'teacher' %} <form method=post action="{{ url_for('delete_material_page', material_id=material['material_id']) }}" style="display:inline"><button type=submit>删除</button></form>{% endif %}</li>{% else %}<li>暂无材料</li>{% endfor %}</ul>"""

MATERIAL_DETAIL_TEMPLATE = """<!doctype html><title>{{ material['filename'] }}</title><h1>{{ material['filename'] }}</h1>
<p><a href="{{ url_for('materials_page') }}">返回材料列表</a> <a href="{{ url_for('download_material', material_id=material['id']) }}">下载原文件</a></p>
<pre>{{ material['content_text'] }}</pre>"""

SEARCH_TEMPLATE = """<!doctype html><title>检索材料</title><h1>检索材料</h1>
<p><a href="{{ url_for('materials_page') }}">返回材料列表</a></p>
<form method=get><label>班级 <select name=class_id>{% for class in classes %}<option value="{{ class['id'] }}" {% if class['id'] == selected_class_id %}selected{% endif %}>{{ class['name'] }}</option>{% endfor %}</select></label>
<label>问题 <input name=query value="{{ query }}" required></label><label>模式 <select name=mode>{% for value in ['keyword', 'vector', 'hybrid'] %}<option value="{{ value }}" {% if value == mode %}selected{% endif %}>{{ value }}</option>{% endfor %}</select></label><button>检索</button></form>
{% if searched %}{% if hits %}<ul>{% for hit in hits %}<li><a href="{{ hit['material_url'] }}">{{ hit['title'] }}</a>：切片 {{ hit['chunk_number'] }}，区间 [{{ hit['char_range']['start'] }}, {{ hit['char_range']['end'] }})<pre>{{ hit['excerpt'] }}</pre></li>{% endfor %}</ul>{% else %}<p>{{ message }}</p>{% endif %}{% endif %}"""


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    auth_secret = (test_config or {}).get("AUTH_SECRET") or os.environ.get("AUTH_SECRET")
    auth_token_secret = (test_config or {}).get("AUTH_TOKEN_SECRET") or os.environ.get("AUTH_TOKEN_SECRET")
    seed_password = (test_config or {}).get("SEED_PASSWORD") or os.environ.get("SEED_PASSWORD")
    if not auth_secret:
        raise RuntimeError("AUTH_SECRET must be set as a server-side environment variable")
    if not auth_token_secret:
        raise RuntimeError("AUTH_TOKEN_SECRET must be set as a server-side environment variable")
    if not seed_password:
        raise RuntimeError("SEED_PASSWORD must be set for repeatable demo data")
    is_testing = bool((test_config or {}).get("TESTING"))
    configured_service = (test_config or {}).get("RETRIEVAL_SERVICE")
    embedding_api_key = (
        (test_config or {}).get("EMBEDDING_API_KEY") or os.environ.get("EMBEDDING_API_KEY")
        or (test_config or {}).get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    )
    embedding_base_url = (test_config or {}).get("EMBEDDING_BASE_URL") or os.environ.get("EMBEDDING_BASE_URL")
    embedding_model = (
        (test_config or {}).get("EMBEDDING_MODEL") or os.environ.get("EMBEDDING_MODEL")
        or (test_config or {}).get("OPENAI_EMBEDDING_MODEL") or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    )
    if test_config and "CHAT_MODEL" in test_config:
        chat_model = test_config["CHAT_MODEL"]
    else:
        chat_model = os.environ.get("CHAT_MODEL", "doubao-seed-2-1-lite-260915")
    if not isinstance(chat_model, str) or not chat_model.strip():
        raise RuntimeError("CHAT_MODEL must be a non-empty server-side configuration value")
    try:
        embedding_dim = int((test_config or {}).get("EMBEDDING_DIM") or os.environ.get("EMBEDDING_DIM", "1536"))
    except ValueError as error:
        raise RuntimeError("EMBEDDING_DIM must be a positive integer") from error
    if embedding_dim <= 0:
        raise RuntimeError("EMBEDDING_DIM must be a positive integer")
    mysql_host = (test_config or {}).get("MYSQL_HOST") or os.environ.get("MYSQL_HOST")
    mysql_database = (test_config or {}).get("MYSQL_DATABASE") or os.environ.get("MYSQL_DATABASE")
    mysql_user = (test_config or {}).get("MYSQL_USER") or os.environ.get("MYSQL_USER")
    mysql_password = (test_config or {}).get("MYSQL_PASSWORD") or os.environ.get("MYSQL_PASSWORD")
    qdrant_url = (test_config or {}).get("QDRANT_URL") or os.environ.get("QDRANT_URL")
    if configured_service is None and not is_testing:
        missing = [
            name for name, value in {
                "EMBEDDING_API_KEY": embedding_api_key, "MYSQL_HOST": mysql_host, "MYSQL_DATABASE": mysql_database,
                "MYSQL_USER": mysql_user, "MYSQL_PASSWORD": mysql_password, "QDRANT_URL": qdrant_url,
            }.items() if not value
        ]
        if missing:
            raise RuntimeError(f"missing server-side retrieval configuration: {', '.join(missing)}")

    app.config.from_mapping(
        SECRET_KEY=auth_secret,
        AUTH_TOKEN_SECRET=auth_token_secret,
        DATABASE_PATH=os.environ.get("DATABASE_PATH", str(Path(app.instance_path) / "campusclaw.db")),
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR", str(Path(app.instance_path) / "uploads")),
        SEED_PASSWORD=seed_password,
        MAX_CONTENT_LENGTH=MAX_FILE_SIZE + MAX_MULTIPART_OVERHEAD,
        MAX_FILE_SIZE=MAX_FILE_SIZE,
        EMBEDDING_BASE_URL=embedding_base_url,
        EMBEDDING_MODEL=embedding_model,
        EMBEDDING_DIM=embedding_dim,
        CHAT_MODEL=chat_model.strip(),
        MCP_DEMO_BASE_URL=os.environ.get("MCP_DEMO_BASE_URL", ""),
        MCP_AUTH_TOKEN=os.environ.get("MCP_AUTH_TOKEN", ""),
        MYSQL_PORT=int(os.environ.get("MYSQL_PORT", "3306")),
        SEED_MATERIALS_DIR=os.environ.get("SEED_MATERIALS_DIR", str(Path(app.instance_path) / "seed-materials")),
    )
    if test_config:
        app.config.update(test_config)

    if configured_service is not None:
        retrieval_service = configured_service
    elif is_testing:
        retrieval_service = RetrievalService(InMemoryChunkStore(), InMemoryVectorStore(), DeterministicEmbedder())
    else:
        mysql_store = MySQLChunkStore(mysql_host, app.config["MYSQL_PORT"], mysql_database, mysql_user, mysql_password)
        vector_store = QdrantVectorStore(qdrant_url, "material_chunks", app.config["EMBEDDING_DIM"])
        mysql_store.initialize()
        vector_store.initialize()
        retrieval_service = RetrievalService(
            mysql_store,
            vector_store,
            OpenAIEmbedder(embedding_api_key, app.config["EMBEDDING_MODEL"], app.config["EMBEDDING_BASE_URL"]),
        )
    app.extensions["retrieval_service"] = retrieval_service
    configured_chat_client = (test_config or {}).get("CHAT_CLIENT")
    app.extensions["chat_client"] = configured_chat_client or OpenAIChatClient(
        embedding_api_key,
        app.config["CHAT_MODEL"],
        embedding_base_url,
    )
    app.extensions["jwt_service"] = JwtService(app.config["AUTH_TOKEN_SECRET"])
    app.extensions["mcp_token_cipher"] = TokenCipher(auth_secret)
    app.extensions["mcp_client_factory"] = (test_config or {}).get("MCP_CLIENT_FACTORY") or HttpMcpClient

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        initialize_database()
        if app.config.get("MCP_DEMO_BASE_URL") and app.config.get("MCP_AUTH_TOKEN"):
            db = get_db()
            class_row = db.execute("SELECT id FROM classes WHERE code = 'class-a'").fetchone()
            teacher = db.execute("SELECT id FROM users WHERE username = 'teacher_a'").fetchone()
            if class_row is not None and teacher is not None:
                db.execute(
                    """INSERT OR IGNORE INTO mcp_servers(
                           class_id, name, base_url, auth_token_ciphertext, created_by
                       ) VALUES (?, 'campus-tools', ?, ?, ?)""",
                    (
                        class_row["id"],
                        normalize_base_url(app.config["MCP_DEMO_BASE_URL"]),
                        app.extensions["mcp_token_cipher"].encrypt(app.config["MCP_AUTH_TOKEN"]),
                        teacher["id"],
                    ),
                )
                db.commit()

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Initialize the SQLite schema and repeatable demo accounts."""
        initialize_database()
        click.echo("database initialized")

    @app.before_request
    def clear_current_user() -> None:
        g.current_user = None
        g.token_claims = None

    def authenticate_bearer(allow_revoked: bool = False) -> bool:
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme != "Bearer" or not token or " " in token:
            return False
        try:
            claims = app.extensions["jwt_service"].decode(token)
        except TokenValidationError:
            return False
        if not allow_revoked and is_token_revoked(claims["jti"]):
            return False
        user = get_user(int(claims["sub"]))
        if user is None:
            return False
        g.current_user = user
        g.token_claims = claims
        return True

    def page_login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not authenticate_bearer():
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    def api_login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not authenticate_bearer():
                return jsonify(error="authentication_required"), 401
            return view(*args, **kwargs)

        return wrapped

    def logout_token_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not authenticate_bearer(allow_revoked=True):
                return jsonify(error="authentication_required"), 401
            return view(*args, **kwargs)

        return wrapped

    def require_class_membership(class_id: int) -> None:
        if not is_member(g.current_user["id"], class_id):
            abort(403)

    def api_document(summary: str, responses: dict | None = None):
        """Attach OpenAPI metadata directly to the Flask handler that implements an endpoint."""
        def decorator(view):
            view.__openapi__ = {"summary": summary, "responses": responses or {"200": {"description": "成功"}}}
            return view

        return decorator

    @app.errorhandler(403)
    def forbidden(_: Exception):
        if request.path.startswith("/api/"):
            return jsonify(error="forbidden"), 403
        return "禁止访问", 403

    @app.errorhandler(404)
    def not_found(_: Exception):
        if request.path.startswith("/api/"):
            return jsonify(error="not_found"), 404
        return "未找到", 404

    @app.errorhandler(413)
    def too_large(_: Exception):
        return jsonify(error="file_too_large"), 413

    @app.get("/health")
    def health():
        try:
            get_db().execute("SELECT 1").fetchone()
        except sqlite3.Error:
            return jsonify(status="unhealthy"), 503
        return jsonify(status="healthy"), 200

    @app.get("/health/retrieval")
    def retrieval_health():
        return jsonify(status="healthy", retrieval="configured"), 200

    @app.get("/login")
    def login():
        return render_template_string(LOGIN_TEMPLATE)

    @app.post("/api/auth/login")
    @api_document("账号密码登录并签发 JWT", {"200": {"description": "返回 Bearer access token"}, "401": {"description": "账号或密码错误"}})
    def token_login():
        payload = request.get_json(silent=True) or request.form
        user = get_user_by_username(payload.get("username", ""))
        password = payload.get("password", "")
        if user is None or not check_password_hash(user["password_hash"], password):
            return jsonify(error="authentication_failed"), 401
        access_token = app.extensions["jwt_service"].issue(user["id"])
        return jsonify(access_token=access_token.value, token_type="Bearer", expires_in=access_token.expires_in)

    @app.post("/api/auth/logout")
    @logout_token_required
    def token_logout():
        revoke_token(g.token_claims["jti"], int(g.token_claims["exp"]))
        return jsonify(status="logged_out")

    @app.post("/logout")
    @page_login_required
    def logout():
        revoke_token(g.token_claims["jti"], int(g.token_claims["exp"]))
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        return redirect(url_for("login"))

    @app.get("/materials")
    def materials_page():
        return redirect(url_for("login"))

    def _member_classes():
        return get_db().execute(
            """SELECT c.id, c.name FROM classes c JOIN class_memberships m ON m.class_id = c.id
               WHERE m.user_id = ? ORDER BY c.id""",
            (g.current_user["id"],),
        ).fetchall()

    @app.get("/api/me/classes")
    @api_login_required
    def my_classes():
        return jsonify(classes=[dict(class_row) for class_row in _member_classes()])

    @app.get("/api/me")
    @api_login_required
    def current_user():
        return jsonify(
            id=g.current_user["id"],
            username=g.current_user["username"],
            display_name=g.current_user["display_name"],
            role=g.current_user["role"],
            classes=[dict(class_row) for class_row in _member_classes()],
        )

    @app.get("/search")
    def search_page():
        return redirect(url_for("login"))

    @app.post("/materials/upload")
    @page_login_required
    def upload_page():
        if g.current_user["role"] != "teacher":
            abort(403)
        _store_material(int(request.form["class_id"]), request.files.get("file"), request.form.get("chunk_strategy", DEFAULT_CHUNK_STRATEGY))
        return redirect(url_for("materials_page"))

    @app.get("/api/classes/<int:class_id>/materials")
    @api_login_required
    def list_materials(class_id: int):
        require_class_membership(class_id)
        records = get_db().execute(
            """SELECT m.id AS material_id, k.id AS knowledge_base_record_id, k.title, m.filename, m.content_type,
                      m.size_bytes, m.created_at
               FROM knowledge_base_records k JOIN materials m ON m.id = k.material_id
               WHERE k.class_id = ? ORDER BY k.id DESC""",
            (class_id,),
        ).fetchall()
        return jsonify(materials=[dict(record) for record in records])

    @app.post("/api/classes/<int:class_id>/materials")
    @api_login_required
    def upload_material(class_id: int):
        if g.current_user["role"] != "teacher":
            abort(403)
        material = _store_material(class_id, request.files.get("file"), request.form.get("chunk_strategy", DEFAULT_CHUNK_STRATEGY))
        return jsonify(material=material), 201

    @app.get("/api/classes/<int:class_id>/search")
    @api_login_required
    def search_materials(class_id: int):
        require_class_membership(class_id)
        query = request.args.get("query", "").strip()
        mode = request.args.get("mode", "hybrid")
        if not query or mode not in {"keyword", "vector", "hybrid"}:
            return jsonify(error="invalid_search_request"), 400
        hits = _search_hits(class_id, query, mode)
        return jsonify(hits=hits, message=None if hits else EMPTY_SEARCH_MESSAGE)

    @app.post("/api/classes/<int:class_id>/questions")
    @api_login_required
    def answer_question(class_id: int):
        require_class_membership(class_id)
        payload = request.get_json(silent=True)
        question = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip() or len(question) > 500:
            return jsonify(error="invalid_question_request"), 400
        result = app.extensions["retrieval_service"].answer_question(class_id, question.strip())
        return jsonify(
            answer=result["answer"],
            keywords=result["keywords"],
            citations=[
                {
                    **{key: value for key, value in citation.items() if key != "material_id"},
                    "material_url": url_for("material_data", material_id=citation["material_id"]),
                }
                for citation in result["citations"]
            ],
        )

    @app.post("/api/classes/<int:class_id>/ai-questions")
    @api_login_required
    def answer_ai_question(class_id: int):
        require_class_membership(class_id)
        payload = request.get_json(silent=True)
        question = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip() or len(question) > 500:
            return jsonify(error="invalid_question_request"), 400
        try:
            result = app.extensions["retrieval_service"].answer_ai_question(
                class_id, question.strip(), app.extensions["chat_client"]
            )
        except AIAnswerUnavailable:
            return jsonify(error="ai_answer_unavailable"), 502
        return jsonify(
            answer=result["answer"],
            citations=[
                {
                    **{key: value for key, value in citation.items() if key != "material_id"},
                    "material_url": url_for("material_data", material_id=citation["material_id"]),
                }
                for citation in result["citations"]
            ],
        )

    def _require_teacher() -> None:
        if g.current_user["role"] != "teacher":
            abort(403)

    def _id_list(value) -> list[int]:
        if value is None:
            return []
        if not isinstance(value, list) or any(isinstance(item, bool) for item in value):
            abort(400, "binding identifiers must be a list")
        try:
            identifiers = [int(item) for item in value]
        except (TypeError, ValueError):
            abort(400, "binding identifiers must be integers")
        if any(item <= 0 for item in identifiers):
            abort(400, "binding identifiers must be positive")
        return list(dict.fromkeys(identifiers))

    def _agent_row(class_id: int, agent_id: int, enabled_only: bool = False):
        query = "SELECT * FROM tutor_agents WHERE id = ? AND class_id = ?"
        parameters: list[object] = [agent_id, class_id]
        if enabled_only:
            query += " AND enabled = 1"
        agent = get_db().execute(query, parameters).fetchone()
        if agent is None:
            abort(404)
        return agent

    def _skill_row(class_id: int, skill_id: int):
        skill = get_db().execute(
            "SELECT * FROM skills WHERE id = ? AND class_id = ?", (skill_id, class_id)
        ).fetchone()
        if skill is None:
            abort(404)
        return skill

    def _bound_ids(agent_id: int, table: str, column: str) -> list[int]:
        return [
            row[column]
            for row in get_db().execute(
                f"SELECT {column} FROM {table} WHERE agent_id = ? ORDER BY {column}", (agent_id,)
            ).fetchall()
        ]

    def _serialize_agent(agent) -> dict:
        return {
            "id": agent["id"],
            "class_id": agent["class_id"],
            "name": agent["name"],
            "prompt": agent["prompt"],
            "enabled": bool(agent["enabled"]),
            "skill_ids": _bound_ids(agent["id"], "tutor_agent_skills", "skill_id"),
            "material_ids": _bound_ids(agent["id"], "tutor_agent_materials", "material_id"),
        }

    def _serialize_skill(skill) -> dict:
        return {
            "id": skill["id"],
            "class_id": skill["class_id"],
            "name": skill["name"],
            "trigger_text": skill["trigger_text"],
            "subject_text": skill["subject_text"],
            "tools": json.loads(skill["tools_json"]),
            "description": skill["description"],
            "source_text": skill["source_text"],
            "enabled": bool(skill["enabled"]),
        }

    def _validate_bindings(class_id: int, skill_ids: list[int], material_ids: list[int]) -> None:
        db = get_db()
        for identifiers, table in ((skill_ids, "skills"), (material_ids, "materials")):
            if not identifiers:
                continue
            placeholders = ",".join("?" for _ in identifiers)
            rows = db.execute(
                f"SELECT id FROM {table} WHERE class_id = ? AND id IN ({placeholders})",
                [class_id, *identifiers],
            ).fetchall()
            if {row["id"] for row in rows} != set(identifiers):
                abort(404)

    def _replace_agent_bindings(agent_id: int, skill_ids: list[int], material_ids: list[int]) -> None:
        db = get_db()
        db.execute("DELETE FROM tutor_agent_skills WHERE agent_id = ?", (agent_id,))
        db.execute("DELETE FROM tutor_agent_materials WHERE agent_id = ?", (agent_id,))
        db.executemany(
            "INSERT INTO tutor_agent_skills(agent_id, skill_id) VALUES (?, ?)",
            [(agent_id, skill_id) for skill_id in skill_ids],
        )
        db.executemany(
            "INSERT INTO tutor_agent_materials(agent_id, material_id) VALUES (?, ?)",
            [(agent_id, material_id) for material_id in material_ids],
        )

    @app.get("/api/classes/<int:class_id>/agents")
    @api_document("列出本班智能体")
    @api_login_required
    def list_agents(class_id: int):
        require_class_membership(class_id)
        query = "SELECT * FROM tutor_agents WHERE class_id = ?"
        if g.current_user["role"] != "teacher":
            query += " AND enabled = 1"
        agents = get_db().execute(query + " ORDER BY id", (class_id,)).fetchall()
        return jsonify(agents=[_serialize_agent(agent) for agent in agents])

    @app.get("/api/classes/<int:class_id>/agents/<int:agent_id>")
    @api_login_required
    def get_agent(class_id: int, agent_id: int):
        require_class_membership(class_id)
        agent = _agent_row(class_id, agent_id, enabled_only=g.current_user["role"] != "teacher")
        return jsonify(agent=_serialize_agent(agent))

    def _agent_input(class_id: int, existing=None):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            abort(400, "JSON body required")
        name = payload.get("name", existing["name"] if existing is not None else "")
        prompt = payload.get("prompt", existing["prompt"] if existing is not None else "")
        enabled = payload.get("enabled", bool(existing["enabled"]) if existing is not None else True)
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > MAX_AGENT_NAME_LENGTH:
            abort(400, "agent name must contain 1 to 64 characters")
        if not isinstance(prompt, str) or len(prompt) > MAX_AGENT_PROMPT_LENGTH:
            abort(400, "agent prompt cannot exceed 2000 characters")
        if not isinstance(enabled, bool):
            abort(400, "enabled must be boolean")
        skill_ids = _id_list(payload.get("skill_ids", _bound_ids(existing["id"], "tutor_agent_skills", "skill_id") if existing is not None else []))
        material_ids = _id_list(payload.get("material_ids", _bound_ids(existing["id"], "tutor_agent_materials", "material_id") if existing is not None else []))
        _validate_bindings(class_id, skill_ids, material_ids)
        return name.strip(), prompt.strip(), enabled, skill_ids, material_ids

    @app.post("/api/classes/<int:class_id>/agents")
    @api_document("教师创建智能体", {"201": {"description": "智能体已创建"}, "403": {"description": "仅教师可写"}})
    @api_login_required
    def create_agent(class_id: int):
        require_class_membership(class_id)
        _require_teacher()
        name, prompt, enabled, skill_ids, material_ids = _agent_input(class_id)
        db = get_db()
        try:
            cursor = db.execute(
                "INSERT INTO tutor_agents(class_id, name, prompt, enabled) VALUES (?, ?, ?, ?)",
                (class_id, name, prompt, int(enabled)),
            )
            _replace_agent_bindings(cursor.lastrowid, skill_ids, material_ids)
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return jsonify(error="agent_name_conflict"), 400
        return jsonify(agent=_serialize_agent(_agent_row(class_id, cursor.lastrowid))), 201

    @app.put("/api/classes/<int:class_id>/agents/<int:agent_id>")
    @app.patch("/api/classes/<int:class_id>/agents/<int:agent_id>")
    @api_document("教师修改、启用或停用智能体")
    @api_login_required
    def update_agent(class_id: int, agent_id: int):
        require_class_membership(class_id)
        _require_teacher()
        agent = _agent_row(class_id, agent_id)
        name, prompt, enabled, skill_ids, material_ids = _agent_input(class_id, agent)
        db = get_db()
        try:
            db.execute(
                "UPDATE tutor_agents SET name = ?, prompt = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, prompt, int(enabled), agent_id),
            )
            _replace_agent_bindings(agent_id, skill_ids, material_ids)
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return jsonify(error="agent_name_conflict"), 400
        return jsonify(agent=_serialize_agent(_agent_row(class_id, agent_id)))

    def _mcp_server_row(class_id: int, server_id: int):
        server = get_db().execute(
            "SELECT * FROM mcp_servers WHERE id = ? AND class_id = ?", (server_id, class_id)
        ).fetchone()
        if server is None:
            abort(404)
        return server

    def _mcp_server_tools(server_id: int) -> list[dict]:
        rows = get_db().execute(
            "SELECT name, description, input_schema_json, discovered_at FROM mcp_tools WHERE server_id = ? ORDER BY name",
            (server_id,),
        ).fetchall()
        return [
            {
                "name": row["name"],
                "description": row["description"],
                "input_schema": json.loads(row["input_schema_json"]),
                "discovered_at": row["discovered_at"],
            }
            for row in rows
        ]

    def _serialize_mcp_server(server, include_tools: bool = False) -> dict:
        result = {
            "id": server["id"],
            "class_id": server["class_id"],
            "name": server["name"],
            "base_url": server["base_url"],
            "status": server["status"],
            "last_error": server["last_error"],
            "connected_at": server["connected_at"],
            "created_at": server["created_at"],
            "updated_at": server["updated_at"],
        }
        if include_tools:
            result["tools"] = _mcp_server_tools(server["id"])
        return result

    def _new_mcp_client(server):
        token = app.extensions["mcp_token_cipher"].decrypt(server["auth_token_ciphertext"])
        return app.extensions["mcp_client_factory"](server["base_url"], token)

    @app.get("/api/classes/<int:class_id>/mcp-servers")
    @api_document("教师列出本班登记的 MCP 服务器，响应不包含令牌", {"200": {"description": "服务器列表"}, "403": {"description": "仅教师可访问"}})
    @api_login_required
    def list_mcp_servers(class_id: int):
        require_class_membership(class_id)
        _require_teacher()
        rows = get_db().execute(
            "SELECT * FROM mcp_servers WHERE class_id = ? ORDER BY id", (class_id,)
        ).fetchall()
        return jsonify(servers=[_serialize_mcp_server(row, include_tools=True) for row in rows])

    @app.post("/api/classes/<int:class_id>/mcp-servers")
    @api_document("教师登记或更新本班 MCP 服务器", {"201": {"description": "登记成功"}, "200": {"description": "同名服务器已更新"}, "403": {"description": "仅教师可写"}})
    @api_login_required
    def register_mcp_server(class_id: int):
        require_class_membership(class_id)
        _require_teacher()
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="invalid_mcp_server", message="请提交 JSON 对象"), 400
        name, token = payload.get("name"), payload.get("token")
        if not isinstance(name, str) or not SERVER_NAME_PATTERN.fullmatch(name.strip()):
            return jsonify(error="invalid_mcp_server", message="服务器名称须以小写字母开头，且只能包含小写字母、数字、下划线或连字符"), 400
        if not isinstance(token, str) or not token or len(token) > 2048:
            return jsonify(error="invalid_mcp_server", message="Bearer 令牌不能为空且不能超过 2048 字符"), 400
        try:
            base_url = normalize_base_url(payload.get("base_url"))
        except ValueError as error:
            return jsonify(error="invalid_mcp_server", message=str(error)), 400
        db = get_db()
        existing = db.execute(
            "SELECT * FROM mcp_servers WHERE class_id = ? AND name = ?", (class_id, name.strip())
        ).fetchone()
        ciphertext = app.extensions["mcp_token_cipher"].encrypt(token)
        if existing is None:
            cursor = db.execute(
                """INSERT INTO mcp_servers(class_id, name, base_url, auth_token_ciphertext, created_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (class_id, name.strip(), base_url, ciphertext, g.current_user["id"]),
            )
            server_id, status = cursor.lastrowid, 201
        else:
            server_id, status = existing["id"], 200
            db.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
            db.execute(
                """UPDATE mcp_servers SET base_url = ?, auth_token_ciphertext = ?, status = 'disconnected',
                   last_error = NULL, connected_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (base_url, ciphertext, server_id),
            )
        db.commit()
        return jsonify(server=_serialize_mcp_server(_mcp_server_row(class_id, server_id), include_tools=True)), status

    @app.post("/api/classes/<int:class_id>/mcp-servers/<int:server_id>/connect")
    @api_document("教师连接 MCP 服务器并缓存 tools/list", {"200": {"description": "握手和工具发现成功"}, "502": {"description": "远端连接失败"}})
    @api_login_required
    def connect_mcp_server(class_id: int, server_id: int):
        require_class_membership(class_id)
        _require_teacher()
        server = _mcp_server_row(class_id, server_id)
        db = get_db()
        try:
            client = _new_mcp_client(server)
            client.initialize()
            tools = client.list_tools()
        except McpError as error:
            message = str(error)[:300]
            db.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
            db.execute(
                """UPDATE mcp_servers SET status = 'error', last_error = ?, connected_at = NULL,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (message, server_id),
            )
            db.commit()
            return jsonify(error="mcp_connection_failed", message=message), 502
        db.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
        db.executemany(
            """INSERT INTO mcp_tools(server_id, name, description, input_schema_json)
               VALUES (?, ?, ?, ?)""",
            [
                (server_id, tool["name"], tool["description"], json.dumps(tool["inputSchema"], ensure_ascii=False))
                for tool in tools
            ],
        )
        db.execute(
            """UPDATE mcp_servers SET status = 'connected', last_error = NULL,
               connected_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (server_id,),
        )
        db.commit()
        return jsonify(server=_serialize_mcp_server(_mcp_server_row(class_id, server_id), include_tools=True))

    @app.post("/api/classes/<int:class_id>/mcp-servers/<int:server_id>/disconnect")
    @api_document("教师断开 MCP 服务器并清空工具缓存")
    @api_login_required
    def disconnect_mcp_server(class_id: int, server_id: int):
        require_class_membership(class_id)
        _require_teacher()
        _mcp_server_row(class_id, server_id)
        db = get_db()
        db.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
        db.execute(
            """UPDATE mcp_servers SET status = 'disconnected', last_error = NULL,
               connected_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (server_id,),
        )
        db.commit()
        return jsonify(server=_serialize_mcp_server(_mcp_server_row(class_id, server_id), include_tools=True))

    @app.get("/api/classes/<int:class_id>/mcp-tools")
    @api_document("教师查看本班已连接 MCP 服务器的工具缓存")
    @api_login_required
    def list_mcp_tools(class_id: int):
        require_class_membership(class_id)
        _require_teacher()
        rows = get_db().execute(
            """SELECT t.name, t.description, t.input_schema_json, t.discovered_at,
                      s.id AS server_id, s.name AS server_name
               FROM mcp_tools t JOIN mcp_servers s ON s.id = t.server_id
               WHERE s.class_id = ? AND s.status = 'connected'
               ORDER BY s.name, t.name""",
            (class_id,),
        ).fetchall()
        return jsonify(
            tools=[
                {
                    "ref": f"{row['name']}@{row['server_name']}",
                    "name": row["name"],
                    "server_id": row["server_id"],
                    "server_name": row["server_name"],
                    "description": row["description"],
                    "input_schema": json.loads(row["input_schema_json"]),
                    "discovered_at": row["discovered_at"],
                }
                for row in rows
            ]
        )

    @app.get("/api/classes/<int:class_id>/mcp-audit")
    @api_document("教师查看本班 MCP 工具调用审计")
    @api_login_required
    def list_mcp_audit(class_id: int):
        require_class_membership(class_id)
        _require_teacher()
        rows = get_db().execute(
            """SELECT a.id, a.tool_ref, a.status, a.details, a.created_at,
                      u.username, u.display_name, s.name AS server_name
               FROM mcp_audit_logs a
               JOIN users u ON u.id = a.user_id
               LEFT JOIN mcp_servers s ON s.id = a.server_id
               WHERE a.class_id = ? ORDER BY a.id DESC LIMIT 100""",
            (class_id,),
        ).fetchall()
        return jsonify(audit=[dict(row) for row in rows])

    def _validate_skill_tools(class_id: int, tools: list[str]) -> None:
        db = get_db()
        for reference in tools:
            if reference == "knowledge_search":
                continue
            match = TOOL_REFERENCE_PATTERN.fullmatch(reference)
            if match is None:
                raise SkillValidationError(f"MCP 工具引用格式无效：{reference}")
            tool_name, server_name = match.groups()
            found = db.execute(
                """SELECT 1 FROM mcp_tools t JOIN mcp_servers s ON s.id = t.server_id
                   WHERE s.class_id = ? AND s.name = ? AND s.status = 'connected' AND t.name = ?""",
                (class_id, server_name, tool_name),
            ).fetchone()
            if found is None:
                raise SkillValidationError(f"MCP 工具未连接、未发现或不属于本班：{reference}")

    @app.get("/api/classes/<int:class_id>/skills")
    @api_document("列出本班技能")
    @api_login_required
    def list_skills(class_id: int):
        require_class_membership(class_id)
        rows = get_db().execute("SELECT * FROM skills WHERE class_id = ? ORDER BY id", (class_id,)).fetchall()
        return jsonify(skills=[_serialize_skill(row) for row in rows])

    @app.get("/api/classes/<int:class_id>/skills/<int:skill_id>")
    @api_login_required
    def get_skill(class_id: int, skill_id: int):
        require_class_membership(class_id)
        return jsonify(skill=_serialize_skill(_skill_row(class_id, skill_id)))

    def _skill_source_from_request() -> str:
        uploaded = request.files.get("file")
        if uploaded is not None:
            try:
                return uploaded.read().decode("utf-8")
            except UnicodeDecodeError:
                raise SkillValidationError("技能文件必须是 UTF-8 文本")
        payload = request.get_json(silent=True)
        if isinstance(payload, dict) and isinstance(payload.get("source_text"), str):
            return payload["source_text"]
        raise SkillValidationError("请提供技能文件或 source_text")

    def _save_skill(class_id: int, skill_id: int | None = None):
        try:
            parsed = parse_skill_source(_skill_source_from_request())
            _validate_skill_tools(class_id, json.loads(parsed["tools_json"]))
        except SkillValidationError as error:
            return jsonify(error="invalid_skill", message=str(error)), 400
        db = get_db()
        try:
            if skill_id is None:
                cursor = db.execute(
                    """INSERT INTO skills(class_id, name, trigger_text, subject_text, tools_json, description, source_text, enabled)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (class_id, parsed["name"], parsed["trigger_text"], parsed["subject_text"], parsed["tools_json"], parsed["description"], parsed["source_text"], parsed["enabled"]),
                )
                skill_id = cursor.lastrowid
                status = 201
            else:
                _skill_row(class_id, skill_id)
                db.execute(
                    """UPDATE skills SET name = ?, trigger_text = ?, subject_text = ?, tools_json = ?,
                       description = ?, source_text = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                    (parsed["name"], parsed["trigger_text"], parsed["subject_text"], parsed["tools_json"], parsed["description"], parsed["source_text"], parsed["enabled"], skill_id),
                )
                status = 200
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return jsonify(error="skill_name_conflict"), 400
        return jsonify(skill=_serialize_skill(_skill_row(class_id, skill_id))), status

    @app.post("/api/classes/<int:class_id>/skills")
    @api_document("教师上传并解析技能文件", {"201": {"description": "技能已创建"}, "400": {"description": "技能文件无效"}})
    @api_login_required
    def create_skill(class_id: int):
        require_class_membership(class_id)
        _require_teacher()
        return _save_skill(class_id)

    @app.put("/api/classes/<int:class_id>/skills/<int:skill_id>")
    @api_login_required
    def update_skill(class_id: int, skill_id: int):
        require_class_membership(class_id)
        _require_teacher()
        return _save_skill(class_id, skill_id)

    @app.delete("/api/classes/<int:class_id>/skills/<int:skill_id>")
    @api_login_required
    def delete_skill(class_id: int, skill_id: int):
        require_class_membership(class_id)
        _require_teacher()
        _skill_row(class_id, skill_id)
        db = get_db()
        db.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        db.commit()
        return jsonify(status="deleted")

    def _conversation_row(conversation_id: int):
        conversation = get_db().execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, g.current_user["id"]),
        ).fetchone()
        if conversation is None or not is_member(g.current_user["id"], conversation["class_id"]):
            abort(404)
        return conversation

    def _serialize_conversation(conversation, include_messages: bool = False) -> dict:
        result = {
            "id": conversation["id"],
            "class_id": conversation["class_id"],
            "agent_id": conversation["agent_id"],
            "skill_ids": [
                row["skill_id"]
                for row in get_db().execute(
                    "SELECT skill_id FROM conversation_skills WHERE conversation_id = ? ORDER BY skill_id",
                    (conversation["id"],),
                ).fetchall()
            ],
            "available_skill_ids": [
                row["id"]
                for row in get_db().execute(
                    """SELECT s.id FROM skills s
                       JOIN tutor_agent_skills binding ON binding.skill_id = s.id
                       WHERE binding.agent_id = ? AND s.enabled = 1 ORDER BY s.id""",
                    (conversation["agent_id"],),
                ).fetchall()
            ],
            "title": conversation["title"],
            "created_at": conversation["created_at"],
            "updated_at": conversation["updated_at"],
        }
        if include_messages:
            rows = get_db().execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation["id"],)
            ).fetchall()
            result["messages"] = [
                {
                    "id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "citations": json.loads(row["citations_json"]),
                    "skill_name": row["skill_name"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        return result

    @app.get("/api/classes/<int:class_id>/conversations")
    @api_document("列出当前用户在本班的会话")
    @api_login_required
    def list_conversations(class_id: int):
        require_class_membership(class_id)
        rows = get_db().execute(
            """SELECT * FROM conversations WHERE class_id = ? AND user_id = ?
               ORDER BY updated_at DESC, id DESC""",
            (class_id, g.current_user["id"]),
        ).fetchall()
        return jsonify(conversations=[_serialize_conversation(row) for row in rows])

    @app.post("/api/classes/<int:class_id>/conversations")
    @api_document("选择已启用智能体和要加载的技能新建会话", {"201": {"description": "会话已创建"}, "400": {"description": "技能选择无效"}, "404": {"description": "智能体不可选或不存在"}})
    @api_login_required
    def create_conversation(class_id: int):
        require_class_membership(class_id)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("agent_id"), int):
            available = get_db().execute(
                "SELECT 1 FROM tutor_agents WHERE class_id = ? AND enabled = 1 LIMIT 1", (class_id,)
            ).fetchone()
            if available is None:
                return jsonify(error="no_enabled_agent"), 400
            return jsonify(error="agent_id_required"), 400
        agent = _agent_row(class_id, payload["agent_id"], enabled_only=True)
        available_skill_ids = {
            row["id"] for row in _agent_skills(agent["id"])
        }
        skill_ids = _id_list(payload["skill_ids"]) if "skill_ids" in payload else sorted(available_skill_ids)
        if not set(skill_ids).issubset(available_skill_ids):
            return jsonify(error="invalid_skill_selection", message="只能加载该智能体已开放且启用的技能"), 400
        db = get_db()
        cursor = db.execute(
            "INSERT INTO conversations(class_id, user_id, agent_id, skill_selection_initialized) VALUES (?, ?, ?, 1)",
            (class_id, g.current_user["id"], agent["id"]),
        )
        db.executemany(
            "INSERT INTO conversation_skills(conversation_id, skill_id) VALUES (?, ?)",
            [(cursor.lastrowid, skill_id) for skill_id in skill_ids],
        )
        db.commit()
        return jsonify(conversation=_serialize_conversation(_conversation_row(cursor.lastrowid))), 201

    @app.get("/api/conversations/<int:conversation_id>")
    @api_document("读取当前用户的会话与消息", {"200": {"description": "会话详情"}, "404": {"description": "会话不存在或不可见"}})
    @api_login_required
    def get_conversation(conversation_id: int):
        return jsonify(conversation=_serialize_conversation(_conversation_row(conversation_id), include_messages=True))

    def _agent_skills(agent_id: int) -> list[dict]:
        rows = get_db().execute(
            """SELECT s.* FROM skills s JOIN tutor_agent_skills b ON b.skill_id = s.id
               WHERE b.agent_id = ? AND s.enabled = 1 ORDER BY s.id""",
            (agent_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _conversation_skills(conversation_id: int, agent_id: int) -> list[dict]:
        rows = get_db().execute(
            """SELECT s.* FROM skills s
               JOIN conversation_skills selected ON selected.skill_id = s.id
               JOIN tutor_agent_skills allowed ON allowed.skill_id = s.id AND allowed.agent_id = ?
               WHERE selected.conversation_id = ? AND s.enabled = 1
               ORDER BY s.id""",
            (agent_id, conversation_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def _execute_skill_tools(class_id: int, skill: dict | None, question: str) -> list[dict[str, str]]:
        if skill is None:
            return []
        db = get_db()
        results: list[dict[str, str]] = []
        for reference in json.loads(skill.get("tools_json") or "[]"):
            if reference == "knowledge_search":
                continue
            match = TOOL_REFERENCE_PATTERN.fullmatch(reference)
            server = None
            status, text, details = "denied", "", "工具引用无效或不属于本班"
            if match is not None:
                tool_name, server_name = match.groups()
                server = db.execute(
                    "SELECT * FROM mcp_servers WHERE class_id = ? AND name = ?",
                    (class_id, server_name),
                ).fetchone()
                cached = None
                if server is not None:
                    cached = db.execute(
                        "SELECT 1 FROM mcp_tools WHERE server_id = ? AND name = ?",
                        (server["id"], tool_name),
                    ).fetchone()
                if server is None or server["status"] != "connected" or cached is None:
                    details = "服务器未连接、工具未发现或工具不属于本班"
                else:
                    try:
                        text = _new_mcp_client(server).call_tool(tool_name, {"question": question})
                        status, details = "ok", "调用成功"
                    except McpUnauthorized:
                        status, details = "denied", "远端拒绝 Bearer 令牌"
                    except McpError as error:
                        status, details = "error", str(error)[:300]
            db.execute(
                """INSERT INTO mcp_audit_logs(class_id, server_id, tool_ref, status, user_id, details)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (class_id, server["id"] if server is not None else None, reference, status, g.current_user["id"], details),
            )
            results.append({"ref": reference, "status": status, "text": text})
        db.commit()
        return results

    @app.patch("/api/conversations/<int:conversation_id>/skills")
    @api_document("用户调整当前会话加载的技能", {"200": {"description": "技能选择已更新"}, "400": {"description": "技能选择无效"}})
    @api_login_required
    def update_conversation_skills(conversation_id: int):
        conversation = _conversation_row(conversation_id)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or "skill_ids" not in payload:
            return jsonify(error="skill_ids_required", message="请提交 skill_ids"), 400
        skill_ids = _id_list(payload["skill_ids"])
        available_skill_ids = {
            row["id"] for row in _agent_skills(conversation["agent_id"])
        }
        if not set(skill_ids).issubset(available_skill_ids):
            return jsonify(error="invalid_skill_selection", message="只能加载该智能体已开放且启用的技能"), 400
        db = get_db()
        db.execute("DELETE FROM conversation_skills WHERE conversation_id = ?", (conversation_id,))
        db.executemany(
            "INSERT INTO conversation_skills(conversation_id, skill_id) VALUES (?, ?)",
            [(conversation_id, skill_id) for skill_id in skill_ids],
        )
        db.execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (conversation_id,))
        db.commit()
        return jsonify(conversation=_serialize_conversation(_conversation_row(conversation_id)))

    @app.post("/api/conversations/<int:conversation_id>/messages")
    @api_document("SSE 流式提问", {"200": {"description": "meta、delta、done 或 error 事件流"}})
    @api_login_required
    def stream_conversation_message(conversation_id: int):
        conversation = _conversation_row(conversation_id)
        payload = request.get_json(silent=True)
        question = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or len(question.strip()) < 2 or len(question.strip()) > MAX_QUESTION_LENGTH:
            return jsonify(error="invalid_question_request"), 400
        question = question.strip()
        agent = _agent_row(conversation["class_id"], conversation["agent_id"], enabled_only=False)
        skill = route_skill(question, _conversation_skills(conversation_id, agent["id"]))
        tool_results = _execute_skill_tools(conversation["class_id"], skill, question)
        db = get_db()
        has_user_message = db.execute(
            "SELECT 1 FROM messages WHERE conversation_id = ? AND role = 'user' LIMIT 1", (conversation_id,)
        ).fetchone()
        db.execute(
            "INSERT INTO messages(conversation_id, role, content) VALUES (?, 'user', ?)",
            (conversation_id, question),
        )
        if has_user_message is None:
            title = question[:24].strip() or "新的提问"
            db.execute(
                "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, conversation_id),
            )
        else:
            db.execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (conversation_id,))
        db.commit()

        material_ids = _bound_ids(agent["id"], "tutor_agent_materials", "material_id")
        try:
            evidence = app.extensions["retrieval_service"].select_ai_evidence(
                conversation["class_id"], question, material_ids
            )
        except Exception:
            return jsonify(error="retrieval_unavailable"), 503
        if skill is not None and skill.get("subject_text"):
            evidence = [item for item in evidence if skill["subject_text"] in item["title"]]
        evidence = [item for item in evidence if str(item.get("chunk_text", "")).strip()][:MAX_AGENT_EVIDENCE]
        citations = [
            {
                **RetrievalService.serialize_ai_citation(chunk),
                "material_url": url_for("material_data", material_id=chunk["material_id"]),
            }
            for chunk in evidence
        ]
        history_rows = db.execute(
            """SELECT role, content FROM messages WHERE conversation_id = ?
               ORDER BY id DESC LIMIT 6""",
            (conversation_id,),
        ).fetchall()
        history = [dict(row) for row in reversed(history_rows)]
        chat_messages = build_chat_messages(agent["prompt"], skill, history, question, evidence, tool_results)
        meta = {
            "status": "ok",
            "skill": {"id": skill["id"], "name": skill["name"]} if skill is not None else None,
            "citations": citations,
            "tool_calls": [{"ref": item["ref"], "status": item["status"]} for item in tool_results],
        }

        @stream_with_context
        def generate():
            yield sse_event("meta", meta)
            client = app.extensions["chat_client"]
            parts: list[str] = []
            stream_error = None
            try:
                if hasattr(client, "stream_messages"):
                    chunks = client.stream_messages(chat_messages)
                elif hasattr(client, "complete_messages"):
                    answer = client.complete_messages(chat_messages)
                    chunks = (answer[index : index + 40] for index in range(0, len(answer), 40))
                else:
                    answer = client.complete(question, chat_messages[-1]["content"])
                    chunks = (answer[index : index + 40] for index in range(0, len(answer), 40))
                visible_chunks = chunks if evidence else strip_reference_stream(chunks)
                for chunk in visible_chunks:
                    if not isinstance(chunk, str) or not chunk:
                        continue
                    parts.append(chunk)
                    yield sse_event("delta", {"text": chunk})
            except Exception:
                if not parts:
                    yield sse_event("error", {"message": "AI 暂时无法回答，请稍后重试"})
                    return
                stream_error = "回答生成中断，已保留现有内容"

            answer_text = "".join(parts).strip()
            if not answer_text:
                yield sse_event("error", {"message": "AI 未返回有效内容"})
                return
            db = get_db()
            cursor = db.execute(
                """INSERT INTO messages(conversation_id, role, content, citations_json, skill_name)
                   VALUES (?, 'assistant', ?, ?, ?)""",
                (conversation_id, answer_text, json.dumps(citations, ensure_ascii=False), skill["name"] if skill else None),
            )
            db.execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (conversation_id,))
            db.commit()
            if stream_error:
                yield sse_event("error", {"message": stream_error})
                return
            yield sse_event("done", {"message_id": cursor.lastrowid})

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    @app.get("/api/openapi.json")
    def openapi_document():
        paths: dict[str, dict] = {}
        for rule in app.url_map.iter_rules():
            view = app.view_functions[rule.endpoint]
            metadata = getattr(view, "__openapi__", None)
            if metadata is None:
                continue
            path = re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule.rule)
            operations = paths.setdefault(path, {})
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                operations[method.lower()] = metadata
        return jsonify(openapi="3.0.3", info={"title": "CampusClaw Freebird API", "version": "5.0.0"}, paths=paths)

    @app.get("/swagger")
    def swagger_page():
        return render_template_string(
            """<!doctype html><html lang=zh-CN><head><meta charset=utf-8><title>CampusClaw API</title>
            <link rel=stylesheet href=https://unpkg.com/swagger-ui-dist@5/swagger-ui.css></head>
            <body><div id=swagger-ui></div><script src=https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js></script>
            <script>SwaggerUIBundle({url:'/api/openapi.json',dom_id:'#swagger-ui',persistAuthorization:true});</script></body></html>"""
        )

    @app.get("/api/materials/<int:material_id>/download")
    @api_login_required
    def download_material(material_id: int):
        material = _get_material(material_id)
        require_class_membership(material["class_id"])
        return send_from_directory(
            app.config["UPLOAD_DIR"], material["storage_name"], as_attachment=True, download_name=material["filename"]
        )

    @app.get("/api/materials/<int:material_id>")
    @api_login_required
    def material_data(material_id: int):
        material = _get_material(material_id)
        require_class_membership(material["class_id"])
        return jsonify(
            id=material["id"],
            class_id=material["class_id"],
            filename=material["filename"],
            content_text=material["content_text"],
            download_url=url_for("download_material", material_id=material["id"]),
        )

    @app.post("/api/materials/<int:material_id>/delete")
    @api_login_required
    def delete_material_api(material_id: int):
        if g.current_user["role"] != "teacher":
            abort(403)
        material = _get_material(material_id)
        require_class_membership(material["class_id"])
        app.extensions["retrieval_service"].delete_material(material_id)
        _delete_material(material)
        return jsonify(status="deleted")

    @app.post("/api/materials/<int:material_id>/reindex")
    @api_document("教师重建材料索引")
    @api_login_required
    def reindex_material_api(material_id: int):
        _require_teacher()
        material = _get_material(material_id)
        require_class_membership(material["class_id"])
        payload = request.get_json(silent=True) or {}
        strategy = payload.get("chunk_strategy", DEFAULT_CHUNK_STRATEGY)
        if strategy not in VALID_STRATEGIES:
            return jsonify(error="unsupported_chunk_strategy"), 400
        try:
            app.extensions["retrieval_service"].index_material(dict(material), strategy)
        except Exception:
            return jsonify(error="reindex_failed"), 502
        return jsonify(status="reindexed", material_id=material_id, chunk_strategy=strategy)

    @app.get("/materials/<int:material_id>")
    def material_page(material_id: int):
        return redirect(url_for("login"))

    @app.post("/materials/<int:material_id>/delete")
    @page_login_required
    def delete_material_page(material_id: int):
        if g.current_user["role"] != "teacher":
            abort(403)
        material = _get_material(material_id)
        require_class_membership(material["class_id"])
        app.extensions["retrieval_service"].delete_material(material_id)
        _delete_material(material)
        return redirect(url_for("materials_page"))

    def _store_material(class_id: int, uploaded_file, chunk_strategy: str = DEFAULT_CHUNK_STRATEGY):
        require_class_membership(class_id)
        if uploaded_file is None or not uploaded_file.filename:
            abort(400, "file is required")
        filename = uploaded_file.filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not filename or filename in {".", ".."} or "\x00" in filename:
            abort(400, "invalid file name")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".txt", ".md"}:
            abort(400, "only .txt and .md files are supported")
        if chunk_strategy not in VALID_STRATEGIES:
            abort(400, "unsupported chunk strategy")

        file_content = uploaded_file.read()
        if len(file_content) > app.config["MAX_FILE_SIZE"]:
            abort(413)
        try:
            content_text = file_content.decode("utf-8")
        except UnicodeDecodeError:
            abort(400, "file must be UTF-8 text")

        upload_dir = Path(app.config["UPLOAD_DIR"])
        storage_stem = secure_filename(Path(filename).stem) or "material"
        storage_name = f"{uuid.uuid4().hex}_{storage_stem}{suffix}"
        temporary_path = upload_dir / f".{storage_name}.uploading"
        final_path = upload_dir / storage_name
        temporary_path.write_bytes(file_content)
        size_bytes = len(file_content)
        db = get_db()
        try:
            db.execute("BEGIN")
            cursor = db.execute(
                """INSERT INTO materials(class_id, uploaded_by, filename, storage_name, content_type, content_text, size_bytes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (class_id, g.current_user["id"], filename, storage_name, uploaded_file.content_type or "text/plain", content_text, size_bytes),
            )
            material_id = cursor.lastrowid
            record_cursor = db.execute(
                "INSERT INTO knowledge_base_records(material_id, class_id, title) VALUES (?, ?, ?)",
                (material_id, class_id, filename),
            )
            temporary_path.replace(final_path)
            db.commit()
        except Exception:
            db.rollback()
            temporary_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        material = {
            "id": material_id,
            "knowledge_base_record_id": record_cursor.lastrowid,
            "class_id": class_id,
            "filename": filename,
            "size_bytes": size_bytes,
            "content_text": content_text,
        }
        app.extensions["retrieval_service"].index_material(material, chunk_strategy)
        material.pop("content_text")
        return material

    def _get_material(material_id: int):
        material = get_db().execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
        if material is None:
            abort(404)
        return material

    def _delete_material(material) -> None:
        upload_dir = Path(app.config["UPLOAD_DIR"])
        original_path = upload_dir / material["storage_name"]
        temporary_path = upload_dir / f".{material['storage_name']}.deleting"
        if original_path.exists():
            original_path.replace(temporary_path)

        db = get_db()
        try:
            db.execute("BEGIN")
            db.execute("DELETE FROM materials WHERE id = ?", (material["id"],))
            db.commit()
        except Exception:
            db.rollback()
            if temporary_path.exists():
                temporary_path.replace(original_path)
            raise
        temporary_path.unlink(missing_ok=True)

    def _search_hits(class_id: int, query: str, mode: str):
        hits = app.extensions["retrieval_service"].search(class_id, query, mode)
        return [
            RetrievalService.serialize_hit(hit, query, url_for("material_data", material_id=hit["material_id"]))
            for hit in hits
        ]

    @app.cli.command("reindex-materials")
    def reindex_materials_command() -> None:
        materials = get_db().execute("SELECT * FROM materials ORDER BY id").fetchall()
        for material in materials:
            app.extensions["retrieval_service"].index_material(dict(material), DEFAULT_CHUNK_STRATEGY)
        click.echo(f"reindexed {len(materials)} materials")

    def _import_seed_materials() -> None:
        seed_root = Path(app.config["SEED_MATERIALS_DIR"])
        if not seed_root.is_dir():
            return
        db = get_db()
        for class_directory in seed_root.iterdir():
            if not class_directory.is_dir():
                continue
            class_row = db.execute("SELECT id FROM classes WHERE code = ?", (class_directory.name,)).fetchone()
            if class_row is None:
                continue
            uploader = db.execute(
                """SELECT u.id FROM users u JOIN class_memberships m ON m.user_id = u.id
                   WHERE u.role = 'teacher' AND m.class_id = ? ORDER BY u.id LIMIT 1""",
                (class_row["id"],),
            ).fetchone()
            if uploader is None:
                continue
            for source in class_directory.iterdir():
                if not source.is_file() or source.suffix.lower() not in {".txt", ".md"}:
                    continue
                content = source.read_text(encoding="utf-8")
                digest = uuid.uuid5(uuid.NAMESPACE_URL, f"{class_directory.name}:{source.name}:{content}").hex
                filename = secure_filename(source.name)
                storage_name = f"seed_{digest}_{filename}"
                existing = db.execute("SELECT * FROM materials WHERE storage_name = ?", (storage_name,)).fetchone()
                if existing is not None:
                    app.extensions["retrieval_service"].index_material(dict(existing), DEFAULT_CHUNK_STRATEGY)
                    continue
                final_path = Path(app.config["UPLOAD_DIR"]) / storage_name
                final_path.write_text(content, encoding="utf-8")
                cursor = db.execute(
                    """INSERT INTO materials(class_id, uploaded_by, filename, storage_name, content_type, content_text, size_bytes)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (class_row["id"], uploader["id"], filename, storage_name, "text/plain", content, len(content.encode("utf-8"))),
                )
                material_id = cursor.lastrowid
                db.execute(
                    "INSERT INTO knowledge_base_records(material_id, class_id, title) VALUES (?, ?, ?)",
                    (material_id, class_row["id"], filename),
                )
                db.commit()
                app.extensions["retrieval_service"].index_material(
                    {"id": material_id, "class_id": class_row["id"], "filename": filename, "content_text": content}, DEFAULT_CHUNK_STRATEGY
                )

    with app.app_context():
        _import_seed_materials()

    return app
