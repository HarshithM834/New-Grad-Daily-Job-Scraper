/* CareerOps: dependency-free, responsive local dashboard. */
(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const data = {jobs: [], metrics: {}, runs: [], feeds: [], view: 'overview', page: 1, pageSize: 14, selected: null, destinations: null};
  const STAGES = ['Not Applied', 'Applied', 'Coding Assessment', 'Interview', 'Offer', 'Declined/Rejected', ''];
  const COLORS = ['#a5a0ff', '#88cbe2', '#c5a3eb', '#8ec5a5', '#e4c485', '#d99699', '#718198'];
  const ICONS = {
    grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    layers:'<path d="m12 2 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 17l9 5 9-5"/>',
    activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    plug:'<path d="M9 3v6m6-6v6M7 9h10v4a5 5 0 0 1-10 0V9Zm5 9v3"/>',
    download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    arrow:'<path d="M4 12h16m-7-7 7 7-7 7"/>',
    briefcase:'<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18"/>',
    check:'<path d="m4 12 5 5L20 6"/>',
    alert:'<path d="M12 3 2 21h20L12 3Zm0 6v5m0 4h.01"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 3"/>'
  };
  function icon(name){return `<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]||ICONS.grid}</svg>`;}
  function toast(message, error=false){const box=$('#toast');box.textContent=message;box.className=`toast${error?' error':''}`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>box.classList.add('hidden'),3600);}
  function dateLabel(value){if(!value)return 'Not recorded';const d=new Date(value);return Number.isNaN(d.getTime())?'Unknown':new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'}).format(d);}
  function safeLink(value){try{const u=new URL(value);if(!['https:','http:'].includes(u.protocol))return '';return u.href;}catch{return '';}}
  function stageClass(value){return ({'Applied':'applied','Coding Assessment':'assessment','Declined/Rejected':'rejected','Not Applied':'not-applied','Interview':'interview','Offer':'offer'}[value]||'unknown');}
  function stagePill(value){return `<span class="stage-badge ${stageClass(value)}">${escapeHTML(value||'Uncategorized')}</span>`;}
  function sourcePill(value){return `<span class="source-pill ${value==='Unknown'?'unknown':''}">${escapeHTML(value||'Unknown')}</span>`;}
  function metric(name,value,subtitle,symbol='briefcase'){return `<article class="metric-card"><div class="metric-title">${escapeHTML(name)}</div><div class="metric-main">${escapeHTML(value)}</div><div class="metric-bottom">${escapeHTML(subtitle)}</div><div class="metric-corner">${icon(symbol)}</div></article>`;}
  function navigate(view){
    if(!$('#page-'+view))return;
    data.view=view;
    $$('.view').forEach(el=>el.classList.toggle('active',el.id==='page-'+view));
    $$('[data-page]').forEach(el=>{const active=el.dataset.page===view;el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    $$('[data-mobile-page]').forEach(el=>el.classList.toggle('active',el.dataset.mobilePage===view));
    $('#breadcrumb').textContent=({overview:'OVERVIEW',explorer:'JOB EXPLORER',pipeline:'APPLICATION PIPELINE',health:'SYSTEM HEALTH',destinations:'OUTPUT DESTINATIONS'})[view];
    window.scrollTo({top:0,behavior:'smooth'});
    if(view==='destinations'&&!data.destinations)loadDestinations();
  }
  async function request(url, options={}){
    const response=await fetch(url,{cache:'no-store',...options});
    let body;
    try{body=await response.json();}catch{throw Error('Unexpected server response');}
    if(!response.ok)throw Error(body.error||`HTTP ${response.status}`);
    return body;
  }
  async function refresh(){
    try{
      const fresh=await request('/api/state');
      Object.assign(data,fresh);
      $('#error-banner').classList.add('hidden');
      $('#side-jobs-count').textContent=data.jobs.length;
      renderAll();
    }catch(exc){const box=$('#error-banner');box.textContent='Unable to load tracker: '+exc.message;box.classList.remove('hidden');}
  }
  function renderOverview(){
    const m=data.metrics, stages=m.stages||{};
    $('#metric-grid').innerHTML=[
      metric('Total opportunities',m.total||0,'Positions in your tracker','briefcase'),
      metric('Active applications',m.in_progress||0,'Applied, assessment or interview','check'),
      metric('Needs attention',m.todo||0,'Flagged for follow-up','clock'),
      metric('Coding assessments',m.assessments||0,'Currently in assessment','activity')
    ].join('');
    $('#refreshed-label').textContent=`Snapshot ${dateLabel(data.generated_at)}`;
    $('#donut-total').textContent=m.total||0;
    const rows=STAGES.map((stage,i)=>({label:stage||'Uncategorized',count:stages[stage||'Uncategorized']||0,color:COLORS[i]})).filter(x=>x.count);
    let pct=0;const ranges=rows.map(r=>{const start=pct;pct+=100*r.count/Math.max(m.total||0,1);return `${r.color} ${start.toFixed(2)}% ${pct.toFixed(2)}%`;});
    $('#stage-donut').style.background=ranges.length?`conic-gradient(${ranges.join(',')})`:'#273244';
    $('#stage-legend').innerHTML=rows.map(r=>`<div class="legend-row"><span class="legend-dot" style="background:${r.color}"></span><span class="legend-name">${escapeHTML(r.label)}</span><b class="legend-amount">${r.count}</b></div>`).join('')||'<p class="hint">No opportunities yet.</p>';
    const companies={};for(const job of data.jobs){const key=job.company||'Unknown';companies[key]=(companies[key]||0)+1;}
    const leaders=Object.entries(companies).sort((a,b)=>b[1]-a[1]).slice(0,5);const max=Math.max(1,...leaders.map(x=>x[1]));
    $('#companies-chart').innerHTML=leaders.map(([name,n])=>`<div class="company-row"><div class="company-row-label"><span title="${escapeHTML(name)}">${escapeHTML(name)}</span><span>${n} opportunities</span></div><div class="company-track"><div class="company-fill" style="width:${(n/max*100).toFixed(1)}%"></div></div></div>`).join('');
    const runs=data.runs||[];$('#trend-content').innerHTML=runs.length?`<div class="trend-bars">${runs.slice(-9).map(r=>`<div class="trend-bar-wrap" title="${escapeHTML(dateLabel(r.started_at))}: ${Number(r.added||0)} new jobs"><div class="trend-bar" style="height:${Math.max(5,Math.min(100,Number(r.added||0)/Math.max(1,...runs.map(x=>Number(x.added||0)))*100))}%"></div><small>${new Date(r.started_at).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</small></div>`).join('')}</div>`:'<div class="empty-message">No automated runs recorded yet. The chart will populate after the next scrape.</div>';
    const queue=data.jobs.filter(j=>j.todo).slice(0,5);
    $('#queue-pill').textContent=`${m.todo||0} OPEN`;
    $('#queue-list').innerHTML=queue.length?queue.map(j=>`<button type="button" class="queue-item" data-job="${escapeHTML(j.id)}"><span class="queue-role">${escapeHTML(j.role)}</span><span class="queue-company">${escapeHTML(j.company)}</span><span class="queue-arrow">→</span></button>`).join(''):'<p class="empty-message">No jobs marked for action.</p>';
  }
  function filtered(){
    const q=$('#search-input').value.trim().toLowerCase(), stage=$('#stage-filter').value, source=$('#source-filter').value, todo=$('#todo-filter').checked;
    return data.jobs.filter(j=>(!q||[j.company,j.role,j.location,j.notes].some(v=>(v||'').toLowerCase().includes(q)))&&
      (stage==='all'||stage===j.stage)&&(source==='all'||source===j.source)&&(!todo||j.todo));
  }
  function renderExplorer(){
    const rows=filtered();const totalPages=Math.max(1,Math.ceil(rows.length/data.pageSize));data.page=Math.min(totalPages,Math.max(1,data.page));
    const shown=rows.slice((data.page-1)*data.pageSize,data.page*data.pageSize);
    $('#results-count').textContent=`${rows.length} ${rows.length===1?'opportunity':'opportunities'} found`;
    $('#jobs-table-body').innerHTML=shown.map(j=>`<tr tabindex="0" data-job="${escapeHTML(j.id)}" aria-label="${escapeHTML(j.role)} at ${escapeHTML(j.company)}"><td><div class="job-title" title="${escapeHTML(j.role)}">${escapeHTML(j.role)}</div><div class="job-company">${escapeHTML(j.company)}</div></td><td><div class="job-location" title="${escapeHTML(j.location)}">${escapeHTML(j.location||'Not listed')}</div></td><td>${stagePill(j.stage)}</td><td>${sourcePill(j.source)}</td><td><span class="checkmark ${j.todo?'yes':''}">${j.todo?'●':'—'}</span></td><td class="row-arrow">›</td></tr>`).join('')||'<tr><td colspan="6" style="text-align:center;padding:40px;color:#9dadc1">No matching jobs. Try clearing your filters.</td></tr>';
    $('#pagination-label').textContent=`Page ${data.page} / ${totalPages} · ${shown.length} shown`;
    $('#prev-page').disabled=data.page<=1;$('#next-page').disabled=data.page>=totalPages;
  }
  function renderPipeline(){
    const live=STAGES.filter(s=>s), counts=live.map(s=>data.jobs.filter(j=>j.stage===s));
    $('#pipeline-stats').innerHTML=live.map((s,i)=>`<div class="stat-pill"><span>${escapeHTML(s)}</span><b>${counts[i].length}</b></div>`).join('');
    $('#kanban-board').innerHTML=live.map((s,i)=>`<section class="kanban-column"><div class="kanban-head"><span>${escapeHTML(s)}</span><span class="kanban-counter">${counts[i].length}</span></div><div class="kanban-stack">${counts[i].slice(0,30).map(j=>`<button type="button" class="kanban-card" data-job="${escapeHTML(j.id)}"><div class="company-line">${escapeHTML(j.company)}</div><div class="role-line">${escapeHTML(j.role)}</div><div class="location-line">${escapeHTML(j.location||'Location not specified')}</div></button>`).join('')||'<p class="empty-message">No positions</p>'}${counts[i].length>30?`<p class="empty-message">Showing 30 of ${counts[i].length}. Use Job Explorer for more.</p>`:''}</div></section>`).join('');
  }
  function renderHealth(){
    const metrics=data.metrics||{},q=metrics.quality||{},runs=data.runs||[];
    const latest=runs[runs.length-1];const complete=Boolean(latest&&latest.status==='success');
    const alert=$('#health-alert');alert.className=`health-alert ${latest?(complete?'ok':'warning'):''}`;
    alert.innerHTML=latest?(complete?`<span class="health-alert-symbol">✓</span><span>Last recorded scrape succeeded on ${escapeHTML(dateLabel(latest.started_at))}. This does not guarantee external pages are still accessible.</span>`:`<span class="health-alert-symbol">!</span><span>Last recorded scrape failed on ${escapeHTML(dateLabel(latest.started_at))}. Review runner logs.</span>`):'<span class="health-alert-symbol">ⓘ</span><span>No automation history is recorded yet. Feed availability and link resolution remain unverified.</span>';
    $('#health-metrics').innerHTML=[
      metric('Tracked jobs',metrics.total||0,'Current CSV inventory','briefcase'),
      metric('Aggregator links',q.aggregator_links||0,'Historical links needing review','alert'),
      metric('Missing links',q.missing_links||0,'No application URL','search'),
      metric('Run history',runs.length,'Recorded executions','activity')
    ].join('');
    $('#feeds-list').innerHTML=(data.feeds||[]).map(f=>`<div class="feed-row"><div><div class="feed-title"><span class="source-dot indigo"></span>${escapeHTML(f.name)}</div><div class="feed-label">${escapeHTML(f.url)}</div></div><a class="small-link" href="${escapeHTML(f.url)}" target="_blank" rel="noopener noreferrer">Visit ↗</a></div>`).join('');
    const qc=[['Aggregator application links',q.aggregator_links||0],['Missing application URLs',q.missing_links||0],['Potential duplicate rows',q.duplicate_rows||0],['Uncategorized stages',q.uncategorized||0],['Unknown historical sources',q.unknown_source||0]];
    $('#quality-list').innerHTML=qc.map(([label,val])=>`<div class="quality-row"><span class="quality-label">${escapeHTML(label)}</span><span class="quality-value ${val?'warn':''}">${val}</span></div>`).join('');
    $('#run-history').innerHTML=runs.length?`<div class="table-wrap"><table class="run-table"><thead><tr><th>DATE</th><th>STATUS</th><th>FOUND</th><th>ADDED</th><th>UNRESOLVED</th></tr></thead><tbody>${runs.slice(-20).reverse().map(r=>`<tr><td>${escapeHTML(dateLabel(r.started_at))}</td><td>${escapeHTML(r.status||'unknown')}</td><td>${Number(r.scraped||0)}</td><td>${Number(r.added||0)}</td><td>${Number(r.unresolved||0)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="run-history-empty">No scrape history available. The next run will create a timestamped audit entry.</div>';
  }
  function renderAll(){renderOverview();renderExplorer();renderPipeline();renderHealth();}
  function openJob(id){
    const j=data.jobs.find(x=>x.id===id);if(!j)return;data.selected=id;
    const link=safeLink(j.link);
    $('#drawer-body').innerHTML=`<div class="detail-content"><div class="drawer-company">${escapeHTML(j.company)}</div><h2 id="drawer-title">${escapeHTML(j.role)}</h2><div class="drawer-tags">${stagePill(j.stage)} ${sourcePill(j.source)}</div><div class="drawer-location">${escapeHTML(j.location||'Location unavailable')}</div><div class="drawer-divider"></div><div class="detail-section-title">APPLICATION LINK</div>${link?`<a href="${escapeHTML(link)}" class="detail-apply" target="_blank" rel="noopener noreferrer"><div><strong>${j.aggregator?'Aggregated listing':'Open application'}</strong><br><span>${escapeHTML(new URL(link).hostname)}</span></div><b>↗</b></a>`:'<div class="connector-note">No valid application URL recorded.</div>'}<div class="drawer-divider"></div><div class="detail-section-title">TRACK PROGRESS</div><form class="detail-form" id="job-edit-form"><label class="form-field">Application stage<select name="stage">${STAGES.map(s=>`<option value="${escapeHTML(s)}" ${j.stage===s?'selected':''}>${escapeHTML(s||'Uncategorized')}</option>`).join('')}</select></label><label class="checkbox-label"><input name="todo" type="checkbox" ${j.todo?'checked':''}>Mark as needing action</label><label class="form-field">Private notes<textarea name="notes" maxlength="3000" placeholder="Personal notes, follow-ups, interview details...">${escapeHTML(j.notes)}</textarea></label><button class="btn btn-primary detail-save" type="submit">Save changes</button></form><p class="detail-note">Saved locally to the same CSV. Source listings and historical statuses are not changed automatically.</p></div>`;
    $('#drawer-layer').classList.remove('hidden');$('.detail-drawer').focus();
  }
  function closeJob(){data.selected=null;$('#drawer-layer').classList.add('hidden');}
  async function saveJob(form){
    const selected=data.selected;if(!selected)return;const save=$('[type=submit]',form);save.disabled=true;
    const payload={id:selected,stage:form.elements.stage.value,todo:form.elements.todo.checked,notes:form.elements.notes.value};
    try{await request('/api/job',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});await refresh();closeJob();toast('Application updated successfully.');}
    catch(exc){toast('Unable to save: '+exc.message,true);save.disabled=false;}
  }
  function exportFiltered(){const jobs=filtered(),columns=['Company','Role','Link','Location','Stage','To-do','Notes'];const lines=[columns.join(',')];
    for(const j of jobs){const fields=[j.company,j.role,j.link,j.location,j.stage,j.todo?'Yes':'No',j.notes];lines.push(fields.map(v=>`"${String(v||'').replace(/"/g,'""')}"`).join(','));}
    const blob=new Blob(['\ufeff'+lines.join('\r\n')],{type:'text/csv;charset=utf-8;'});const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download='careerops-filtered-jobs.csv';a.click();setTimeout(()=>URL.revokeObjectURL(u),1500);
  }
  const DESCRIPTIONS={
    csv:['CSV tracker','Always available as the source of truth. Your application statuses and notes stay intact.'],
    json:['JSON export','Write a portable structured snapshot to exports/jobs.json.'],
    pdf:['PDF report','Generate a printable professional report with the complete job inventory.'],
    google_sheets:['Google Sheets','Sync to a sheet that you shared with your service account.'],
    webhook:['HTTPS Webhook','Send jobs to your own automation (Make, Zapier, n8n, or custom API).']
  };
  async function loadDestinations(){
    try{data.destinations=await request('/api/destinations');renderDestinations();}
    catch(exc){$('#connector-status').textContent='Could not load: '+exc.message;}
  }
  function renderDestinations(){
    if(!data.destinations)return;
    const cfg=data.destinations;$('#connector-status').textContent='Configured locally · Your credentials are never saved here';
    $('#destination-grid').innerHTML=cfg.destinations.map(d=>{
      const [title,desc]=DESCRIPTIONS[d.type];const fixed=d.type==='csv';
      let fields='';
      if(d.type==='google_sheets')fields=`<label>Spreadsheet ID<input type="text" name="spreadsheet_id" maxlength="200" autocomplete="off" placeholder="Google Sheets ID" value="${escapeHTML(d.spreadsheet_id||'')}"></label><label>Worksheet / tab<input type="text" name="worksheet" maxlength="90" value="${escapeHTML(d.worksheet||'Jobs')}"></label><small style="color:#89a4bc">Service account: ${cfg.credentials.google_sheets?'Configured in environment':'Credential not detected'}</small>`;
      if(d.type==='webhook')fields=`<label>Webhook HTTPS URL<input type="url" name="url" maxlength="2000" autocomplete="off" placeholder="${d.configured?'Configured. Enter a new URL to replace':'https://hooks.example.com/...'}" value=""></label><small style="color:#89a4bc">${d.configured?'Webhook configured (URL hidden)':'No endpoint configured'}</small>`;
      return `<div class="destination-card" data-destination="${d.type}"><div class="destination-head"><div><strong>${escapeHTML(title)}</strong><small>${fixed?'PRIMARY STORAGE':'OPTIONAL CONNECTOR'}</small></div><label class="destination-switch"><input type="checkbox" name="enabled" ${d.enabled?'checked':''} ${fixed?'disabled':''}>${d.enabled?'On':'Off'}</label></div><p>${escapeHTML(desc)}</p>${fields}</div>`;
    }).join('');
  }
  function getDestinationSettings(){return {destinations:data.destinations.destinations.map(d=>{
    const root=$(`[data-destination="${d.type}"]`),enabled=$('[name=enabled]',root).checked;
    const value={type:d.type,enabled};
    if(d.type==='google_sheets'){value.spreadsheet_id=$('[name=spreadsheet_id]',root).value;value.worksheet=$('[name=worksheet]',root).value;}
    if(d.type==='webhook')value.url=$('[name=url]',root).value;
    return value;
  })};}
  async function saveDestinations(){
    const btn=$('#save-destinations');btn.disabled=true;
    try{const result=await request('/api/destinations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(getDestinationSettings())});data.destinations=result.settings;renderDestinations();toast('Destination preferences saved locally.');}
    catch(exc){toast('Could not save destinations: '+exc.message,true);}finally{btn.disabled=false;}
  }
  async function syncDestinations(){
    const btn=$('#sync-destinations');btn.disabled=true;$('#sync-status').textContent='Syncing enabled outputs...';
    try{const result=await request('/api/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const bad=result.results.filter(x=>x.status==='failed');
      $('#sync-status').textContent=bad.length?`${bad.length} connector(s) failed`:`${result.results.length} destination(s) synced`;
      if(bad.length)toast(bad.map(x=>x.type+': '+x.error).join('; '),true);else toast('Output synchronization completed.');
    }catch(exc){$('#sync-status').textContent='Sync failed';toast(exc.message,true);}finally{btn.disabled=false;}
  }
  function wire(){
    $$('[data-icon]').forEach(x=>x.innerHTML=icon(x.dataset.icon));
    $('#today-label').textContent=new Intl.DateTimeFormat('en-US',{weekday:'short',month:'short',day:'numeric',year:'numeric'}).format(new Date());
    $$('[data-page]').forEach(btn=>btn.addEventListener('click',()=>navigate(btn.dataset.page)));
    $$('[data-mobile-page]').forEach(btn=>btn.addEventListener('click',()=>navigate(btn.dataset.mobilePage)));
    $$('[data-navigate]').forEach(btn=>btn.addEventListener('click',()=>navigate(btn.dataset.navigate)));
    $('#overview-explore').addEventListener('click',()=>navigate('explorer'));
    $('#view-queue').addEventListener('click',()=>{$('#todo-filter').checked=true;navigate('explorer');renderExplorer();});
    $('#overview-export').addEventListener('click',()=>location.assign('/download/tracker.csv'));
    $('#explorer-export').addEventListener('click',exportFiltered);
    ['search-input','stage-filter','source-filter','todo-filter'].forEach(id=>$('#'+id).addEventListener(id==='search-input'?'input':'change',()=>{data.page=1;renderExplorer();}));
    $('#prev-page').addEventListener('click',()=>{data.page--;renderExplorer();});
    $('#next-page').addEventListener('click',()=>{data.page++;renderExplorer();});
    document.addEventListener('click',e=>{const item=e.target.closest('[data-job]');if(item)openJob(item.dataset.job);});
    document.addEventListener('keydown',e=>{if(e.key==='Escape')closeJob();if((e.key==='Enter'||e.key===' ')&&e.target.matches('tr[data-job]')){e.preventDefault();openJob(e.target.dataset.job);}});
    $('#close-drawer').addEventListener('click',closeJob);$('#drawer-backdrop').addEventListener('click',closeJob);
    $('#drawer-body').addEventListener('submit',e=>{if(e.target.id==='job-edit-form'){e.preventDefault();saveJob(e.target);}});
    $('#save-destinations').addEventListener('click',saveDestinations);
    $('#sync-destinations').addEventListener('click',syncDestinations);
    $$('[data-page]').forEach(b=>{if(b.dataset.page===data.view)b.classList.add('active');});
    refresh();
  }
  wire();
})();