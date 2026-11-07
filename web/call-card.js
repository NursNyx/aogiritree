const callCard = {
  seconds(timestamp) {
    const parts = String(timestamp || '0').split(':').map(Number);
    return parts.length === 2 ? parts[0] * 60 + parts[1] : (parts[0] || 0);
  },
  render(conversation, result) {
    const root = document.querySelector('#callCard');
    if (conversation.channel !== 'voice call') { root.innerHTML = ''; return; }
    const audio = conversation.audio_url;
    const duration = Math.max(1, ...conversation.transcript.map(turn => this.seconds(turn.timestamp)));
    const score = result?.score?.final_score;
    root.innerHTML = `<section class="call-card">
      <div class="call-card-top"><div><small>КАРТОЧКА ЗВОНКА</small><h3>Запись разговора</h3></div><span class="call-duration">${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')}</span></div>
      ${audio ? `<audio id="callAudio" controls preload="metadata" src="${esc(audio)}"></audio>` : `<div class="audio-unavailable"><span>♪</span><div><b>Аудиозапись не приложена</b><small>Можно прослушать расшифровку и перейти к нужному моменту.</small></div></div>`}
      <div class="call-timeline-wrap"><div class="call-timeline" role="list" aria-label="Таймлайн звонка">${conversation.transcript.map((turn, i) => { const pos = Math.min(100, this.seconds(turn.timestamp) / duration * 100); return `<button class="timeline-mark ${turn.speaker}" style="left:${pos}%" title="${esc(turn.timestamp)} · ${esc(turn.speaker)}" aria-label="Перейти к реплике ${i + 1}" data-call-turn="${i + 1}" data-seconds="${this.seconds(turn.timestamp)}"><i></i><span>${i + 1}</span></button>`; }).join('')}</div><div class="timeline-labels"><span>00:00</span><span>${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')}</span></div></div>
      <div class="call-summary"><div><small>ИТОГОВАЯ ОЦЕНКА</small><strong>${score ?? '—'}${score == null ? '' : '<small> / 100</small>'}</strong></div><button class="appeal-open" type="button">Подать апелляцию</button></div>
      <div class="appeal-form" hidden><label>Критерий<select class="appeal-criterion">${(result?.criteria || []).map(x => `<option value="${esc(x.criterion_id)}">${esc(criterionNames[x.criterion_id] || x.criterion_id)}</option>`).join('')}</select></label><label>Комментарий<textarea class="appeal-note" rows="3" placeholder="Объясните, с чем вы не согласны"></textarea></label><div><button class="appeal-cancel" type="button">Отмена</button><button class="appeal-submit primary" type="button">Отправить апелляцию</button></div></div>
      <div class="appeal-status"></div><button class="transcript-jump" type="button">Открыть расшифровку речи ↓</button>
    </section>`;
    root.querySelectorAll('[data-call-turn]').forEach(mark => mark.onclick = () => {
      const turn = Number(mark.dataset.callTurn), player = root.querySelector('#callAudio');
      if (player) player.currentTime = Number(mark.dataset.seconds);
      document.querySelector('[data-tab="transcript"]').click();
      setTimeout(() => document.querySelector(`#turn-${turn}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50);
    });
    root.querySelector('.transcript-jump').onclick = () => {
      document.querySelector('[data-tab="transcript"]').click();
      document.querySelector('#transcript').scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    root.querySelector('.appeal-open').onclick = () => root.querySelector('.appeal-form').hidden = false;
    root.querySelector('.appeal-cancel').onclick = () => root.querySelector('.appeal-form').hidden = true;
    root.querySelector('.appeal-submit').onclick = async () => {
      const note = root.querySelector('.appeal-note').value.trim();
      if (!note) return toast('Добавьте комментарий к апелляции');
      const button = root.querySelector('.appeal-submit'); button.disabled = true;
      try {
        await api('/api/appeals', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ appeal_id: `appeal-${Date.now()}`, conversation_id: conversation.conversation_id, criterion_id: root.querySelector('.appeal-criterion').value, note, status: 'open' }) });
        root.querySelector('.appeal-form').hidden = true;
        root.querySelector('.appeal-status').textContent = 'Апелляция отправлена на рассмотрение';
        toast('Апелляция отправлена');
      } catch (error) { toast(error.message); } finally { button.disabled = false; }
    };
  }
};
