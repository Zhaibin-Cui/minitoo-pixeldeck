'use strict';
(() => {
  const categories = {all:'All 18',system:'System',time:'Time',world:'Pixel worlds',events:'Events',lab:'Labs'};
  const demos = [
    {key:'dashboard',name:'Dashboard',group:'system',short:'Five system monitors. One place to look.',description:'CPU, memory, network, storage and power in one view. Open any metric for a closer look.',action:'Left / Right selects. Activate opens a detail; Activate again returns.'},
    {key:'buddy',name:'Bit Buddy',group:'world',short:'A CRT companion with a heart.',description:'A little CRT companion for the corner of your desk. Animated expressions, tiny hearts and no work to do.',action:'Activate sends a heart.'},
    {key:'rain',name:'Neon Rain',group:'world',short:'A quiet stream of cyan and magenta code.',description:'Columns of cyan and magenta characters fall through a dark pixel sky. A screen-sized pause between tasks.',action:'Activate pauses or resumes the rain.'},
    {key:'orbit',name:'Orbital',group:'world',short:'A ringed planet, a satellite and a little space.',description:'A ringed planet and its satellite trace a small orbit against a field of stars.',action:'Activate pauses or resumes the orbit.'},
    {key:'audio',name:'Audio Lab',group:'lab',short:'A speaker, a microphone and a compact live meter.',description:'Bounded speaker, microphone and duplex exercises. Compact live RMS gives way to full session statistics after stopping.',action:'Select a mode. Hardware audio stays off until explicit endpoints and --audio are supplied.'},
    {key:'pulse',name:'Pulse',group:'system',short:'CPU history and memory usage at a glance.',description:'A live CPU curve and memory bars, drawn from the computer running Pixeldeck.',action:'Activate freezes or resumes measurements.'},
    {key:'network',name:'Net Scope',group:'system',short:'Read the traffic passing through your interfaces.',description:'Aggregate network receive and transmit rates from local interface counters. It sends no speed-test traffic.',action:'Activate freezes or resumes RX / TX readings.'},
    {key:'storage',name:'Volume Vault',group:'system',short:'Free space, without opening another window.',description:'Actual volume capacity and remaining space, labeled without exposing local paths.',action:'Activate selects the next available volume.'},
    {key:'power',name:'Power Cell',group:'system',short:'Battery level, external power and an honest empty state.',description:'Battery and external-power information from the host. A computer without a battery shows NO BATTERY.',action:'Activate switches between compact and detailed views.'},
    {key:'clock',name:'Neon Clock',group:'time',short:'Local time and UTC in pixel lettering.',description:'A wall clock with a local-time and UTC view. Its time source is separate from the monotonic timers.',action:'Activate switches between local time and UTC.'},
    {key:'stopwatch',name:'Stopwatch',group:'time',short:'Elapsed time for an open-ended task.',description:'A stopwatch based on monotonic elapsed time, independent of the number of frames rendered.',action:'Activate starts or pauses. Desktop R resets.'},
    {key:'pomodoro',name:'Pomodoro',group:'time',short:'25 minutes of focus. A five-minute break.',description:'A focus and break timer that tracks elapsed time even when another cartridge is selected.',action:'Activate starts or pauses. Desktop R resets.'},
    {key:'focus',name:'Focus Foundry',group:'time',short:'One minute, counted by a pixel hourglass.',description:'A short focus timer with an animated hourglass. A simple place to check start and pause behavior.',action:'Activate starts or pauses the one-minute timer.'},
    {key:'breathe',name:'Breath Loop',group:'time',short:'A four-phase visual pacing loop.',description:'A 4–4–4–4 sequence of expanding and contracting pixels for a visual pause.',action:'Activate starts or pauses. Desktop R resets.'},
    {key:'build',name:'Build Beacon',group:'events',short:'Let your build script report its own progress.',description:'A generic JSONL-fed build state display. Your producer sends progress and results; Pixeldeck never executes the build.',action:'Activate changes the view. Send events with --stdin.',stdin:true},
    {key:'signal',name:'Signal Inbox',group:'events',short:'A place for the events worth noticing.',description:'Eight recent notices, pushed by your own producer through a local JSONL stream.',action:'Activate clears the inbox. Send notices with --stdin.',stdin:true},
    {key:'buttons',name:'Button Lab',group:'lab',short:'Count what the host actually receives.',description:'An activation counter for keyboard and supported media callbacks. Useful for inspecting the input path.',action:'Activate increments the counter. Host callbacks are not a count of raw physical presses.'},
    {key:'link',name:'Link Lab',group:'lab',short:'Inspect the connection without an upload loop.',description:'Frozen transfer snapshots, input counters and numbered pixel patterns. ACKs collect without triggering new uploads.',action:'Left / Right selects a panel. Activate refreshes or opens detail; desktop Back returns.'}
  ];
  const featuredKeys = ['dashboard','buddy','rain','orbit','audio'];
  const image = document.getElementById('featured-image');
  const picker = document.getElementById('featured-picker');
  const grid = document.getElementById('cartridge-grid');
  const filters = document.getElementById('filters');
  const motionButton = document.getElementById('motion-toggle');
  const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  let selected = 'dashboard';
  let paused = motionQuery.matches;
  let motionOverridden = false;
  const command = demo => `.\\.venv\\Scripts\\pixeldeck.exe run ${demo.key}${demo.stdin ? ' --stdin' : ''}`;
  const asset = (key, animated=false) => `assets/${key}.${animated ? 'gif' : 'png'}`;

  function updateMotion() {
    image.src = asset(selected, !paused);
    motionButton.textContent = paused ? 'Play preview' : 'Pause preview';
    motionButton.setAttribute('aria-pressed', String(paused));
    motionButton.setAttribute('aria-label', paused ? 'Play animated preview' : 'Use a static preview');
  }

  function selectDemo(key, fromShelf=false) {
    const demo = demos.find(item => item.key === key);
    if (!demo) return;
    selected = key;
    const position = demos.indexOf(demo) + 1;
    document.getElementById('featured-category').textContent = `${String(position).padStart(2,'0')} / ${categories[demo.group].toUpperCase()}`;
    document.getElementById('featured-title').textContent = demo.name;
    document.getElementById('featured-description').textContent = demo.description;
    document.getElementById('featured-action').textContent = demo.action;
    document.getElementById('featured-command').textContent = command(demo);
    document.querySelector('[data-copy="featured-command"]').setAttribute('aria-label', `Copy ${demo.name} preview command`);
    image.alt = `${demo.name}: ${demo.short} Synthetic offline program preview.`;
    document.querySelectorAll('[data-demo]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.demo === key)));
    updateMotion();
    if (fromShelf) {
      document.getElementById('showcase').scrollIntoView({behavior:motionQuery.matches ? 'instant' : 'smooth',block:'start'});
      document.getElementById('featured-title').focus({preventScroll:true});
    }
  }

  for (const key of featuredKeys) {
    const demo = demos.find(item => item.key === key);
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'featured-choice'; button.dataset.demo = key;
    button.setAttribute('aria-label', `Preview ${demo.name}`);
    const thumb = document.createElement('img');
    thumb.src = asset(key); thumb.alt = ''; thumb.width = 64; thumb.height = 51;
    const label = document.createElement('span'); label.textContent = demo.name;
    button.append(thumb,label); button.addEventListener('click', () => selectDemo(key));
    picker.append(button);
  }
  picker.addEventListener('keydown', event => {
    const buttons = [...picker.querySelectorAll('button')];
    const current = buttons.indexOf(document.activeElement);
    if (current < 0 || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length-1 :
      (current + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
    buttons[next].focus(); buttons[next].click();
  });

  for (const demo of demos) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'cartridge'; button.dataset.demo = demo.key;
    button.dataset.group = demo.group;
    button.setAttribute('aria-label', `Show ${demo.name} in the large preview. ${demo.short}`);
    const art = document.createElement('div'); art.className = 'cartridge-art';
    const thumb = document.createElement('img');
    thumb.src = asset(demo.key); thumb.alt = ''; thumb.width = 320; thumb.height = 256;
    thumb.loading = 'lazy'; thumb.decoding = 'async'; art.append(thumb);
    const meta = document.createElement('div'); meta.className = 'cartridge-meta';
    const title = document.createElement('h3'); title.textContent = demo.name;
    const tag = document.createElement('span'); tag.className = 'cartridge-tag'; tag.textContent = categories[demo.group];
    meta.append(title,tag);
    const description = document.createElement('p'); description.textContent = demo.short;
    const run = document.createElement('code'); run.className = 'card-command'; run.textContent = command(demo);
    button.append(art,meta,description,run); button.addEventListener('click', () => selectDemo(demo.key,true));
    grid.append(button);
  }

  for (const [key,label] of Object.entries(categories)) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'filter'; button.textContent = label;
    button.setAttribute('aria-pressed', String(key === 'all'));
    button.addEventListener('click', () => {
      filters.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      let count = 0;
      grid.querySelectorAll('.cartridge').forEach(card => {
        card.hidden = key !== 'all' && card.dataset.group !== key;
        if (!card.hidden) count++;
      });
      document.getElementById('gallery-count').textContent = `${count} ${count === 1 ? 'cartridge' : 'cartridges'}`;
    });
    filters.append(button);
  }

  motionButton.hidden = false;
  motionButton.addEventListener('click', () => {motionOverridden = true; paused = !paused; updateMotion();});
  motionQuery.addEventListener('change', event => {if (!motionOverridden) {paused = event.matches; updateMotion();}});

  document.querySelectorAll('[data-copy]').forEach(button => {
    let reset;
    button.addEventListener('click', async () => {
      const target = document.getElementById(button.dataset.copy);
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(target.textContent);
        button.textContent = 'Copied';
        document.getElementById('copy-status').textContent = 'Command copied to clipboard.';
      } catch {
        const range = document.createRange(); range.selectNodeContents(target);
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        button.textContent = 'Selected';
        document.getElementById('copy-status').textContent = 'Clipboard unavailable. Command selected; use your copy shortcut.';
      }
      clearTimeout(reset); reset = setTimeout(() => {button.textContent = 'Copy';},2200);
    });
  });
  selectDemo(selected);
})();
