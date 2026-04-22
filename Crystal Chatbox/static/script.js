let refreshInterval = (window.CONFIG && window.CONFIG.refresh_interval) || 1;
let updateTimer;
let customMessages = [];
let isTyping = false;
let typingDebounceTimer = null;
let fbtSettingsHydrated = false;
let fbtSettingsDirty = false;
let vrcxPlusInitialized = false;
let vrcxPlusData = null;
let vrcxPlusHistorySelectedUserId = '';
let vrcxPlusVrchatStatus = { loggedIn: false, requires2fa: false, methods: [] };
let vrcxPlusAvatarHistoryRefreshTimer = null;
let fbtRecenterEndsAt = 0;
let fbtRecenterTimer = null;

document.addEventListener('DOMContentLoaded', () => {
    safeSetup('setupTabs', setupTabs);
    safeSetup('setupButtons', setupButtons);
    safeSetup('setupLayout', setupLayout);
    safeSetup('setupProgressStyle', setupProgressStyle);
    safeSetup('setupAdvanced', setupAdvanced);
    safeSetup('setupStreamerMode', setupStreamerMode);
    safeSetup('setupTypingFeature', setupTypingFeature);
    safeSetup('setupQuickPhrases', setupQuickPhrases);
    safeSetup('setupAfkTracking', setupAfkTracking);
    safeSetup('setupBodyTracking', setupBodyTracking);
    safeSetup('setupVrcxPlus', setupVrcxPlus);
    safeSetup('setupConfigGears', setupConfigGears);
    safeSetup('loadCustomMessages', loadCustomMessages);
    safeSetup('startUpdate', startUpdate);
});

function safeSetup(name, fn) {
    try {
        fn();
    } catch (e) {
        console.error(`[Init] ${name} failed:`, e);
    }
}

function setupConfigGears() {
    document.querySelectorAll('.config-gear').forEach(gear => {
        gear.addEventListener('click', (e) => {
            e.stopPropagation();
            const sectionId = gear.dataset.section;
            if (!sectionId) return;
            
            const settingsSections = ['music_settings', 'timezone_settings', 'custom_messages_settings'];
            const subtab = settingsSections.includes(sectionId) ? 'settings' : 'advanced';
            showMainTab('chatbox');
            showChatboxSubtab(subtab);
            
            setTimeout(() => {
                const section = document.getElementById(sectionId);
                if (section) {
                    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    section.style.transition = 'background 0.3s ease';
                    section.style.background = 'rgba(0, 191, 255, 0.2)';
                    section.style.borderRadius = '6px';
                    section.style.padding = '4px 8px';
                    section.style.margin = '-4px -8px';
                    setTimeout(() => {
                        section.style.background = '';
                        section.style.padding = '';
                        section.style.margin = '';
                    }, 1500);
                }
            }, 100);
        });
    });
}

function setupTypingFeature() {
    const typingInput = document.getElementById('typing_input');
    const sendBtn = document.getElementById('btn_send_typed');
    const charCount = document.getElementById('typing_char_count');
    const typingStatus = document.getElementById('typing_status');
    
    if (!typingInput || !sendBtn) return;
    
    typingInput.addEventListener('input', () => {
        const len = typingInput.value.length;
        charCount.textContent = `${len}/144`;
        sendBtn.disabled = len === 0;
        
        if (len > 0 && !isTyping) {
            startTyping();
        }
        
        if (typingDebounceTimer) clearTimeout(typingDebounceTimer);
        typingDebounceTimer = setTimeout(() => {
            if (typingInput.value.length === 0 && isTyping) {
                cancelTyping();
            }
        }, 2000);
    });
    
    typingInput.addEventListener('focus', () => {
        if (typingInput.value.length > 0) {
            startTyping();
        }
    });
    
    typingInput.addEventListener('blur', () => {
        if (typingInput.value.length === 0) {
            cancelTyping();
        }
    });
    
    typingInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && typingInput.value.trim()) {
            e.preventDefault();
            sendTypedMessage();
        } else if (e.key === 'Escape') {
            typingInput.value = '';
            charCount.textContent = '0/144';
            sendBtn.disabled = true;
            cancelTyping();
            typingInput.blur();
        }
    });
    
    sendBtn.addEventListener('click', () => {
        if (typingInput.value.trim()) {
            sendTypedMessage();
        }
    });
}

async function startTyping() {
    if (isTyping) return;
    isTyping = true;
    
    const typingInput = document.getElementById('typing_input');
    const typingStatus = document.getElementById('typing_status');
    
    typingInput.classList.add('typing-active');
    typingStatus.textContent = 'Typing... (chatbox paused)';
    typingStatus.classList.remove('sent');
    
    try {
        await fetch('/typing_state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ typing: true })
        });
    } catch (e) {
        console.error('Failed to set typing state:', e);
    }
}

async function cancelTyping() {
    if (!isTyping) return;
    isTyping = false;
    
    const typingInput = document.getElementById('typing_input');
    const typingStatus = document.getElementById('typing_status');
    
    typingInput.classList.remove('typing-active');
    typingStatus.textContent = '';
    
    try {
        await fetch('/cancel_typing', { method: 'POST' });
    } catch (e) {
        console.error('Failed to cancel typing:', e);
    }
}

async function sendTypedMessage() {
    const typingInput = document.getElementById('typing_input');
    const sendBtn = document.getElementById('btn_send_typed');
    const charCount = document.getElementById('typing_char_count');
    const typingStatus = document.getElementById('typing_status');
    
    const message = typingInput.value.trim();
    if (!message) return;
    
    sendBtn.disabled = true;
    typingStatus.textContent = 'Sending...';
    
    try {
        const response = await fetch('/send_typed_message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        
        if (response.ok) {
            typingInput.value = '';
            charCount.textContent = '0/144';
            typingInput.classList.remove('typing-active');
            typingStatus.textContent = 'Message sent!';
            typingStatus.classList.add('sent');
            isTyping = false;
            
            setTimeout(() => {
                typingStatus.textContent = '';
                typingStatus.classList.remove('sent');
            }, 3000);
        } else {
            typingStatus.textContent = 'Failed to send';
            sendBtn.disabled = false;
        }
    } catch (e) {
        console.error('Failed to send typed message:', e);
        typingStatus.textContent = 'Error sending';
        sendBtn.disabled = false;
    }
}

function setupQuickPhrases() {
    const toggleBtn = document.getElementById('btn_toggle_phrases');
    const container = document.getElementById('quick_phrases_container');
    const addBtn = document.getElementById('btn_add_phrase');
    const newPhraseInput = document.getElementById('new_phrase_input');
    
    if (!toggleBtn || !container) return;
    
    toggleBtn.addEventListener('click', () => {
        const isHidden = container.style.display === 'none';
        container.style.display = isHidden ? 'block' : 'none';
        toggleBtn.textContent = isHidden ? 'Hide' : 'Show';
    });
    
    document.querySelectorAll('.quick-phrase-btn').forEach(btn => {
        btn.addEventListener('click', () => sendQuickPhrase(btn.dataset.phrase));
    });
    
    if (addBtn && newPhraseInput) {
        addBtn.addEventListener('click', () => addQuickPhrase());
        newPhraseInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addQuickPhrase();
            }
        });
    }
}

async function sendQuickPhrase(phrase) {
    if (!phrase) return;
    
    try {
        const response = await fetch('/send_quick_phrase', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phrase })
        });
        
        if (response.ok) {
            const typingStatus = document.getElementById('typing_status');
            if (typingStatus) {
                typingStatus.textContent = 'Quick phrase sent!';
                typingStatus.classList.add('sent');
                setTimeout(() => {
                    typingStatus.textContent = '';
                    typingStatus.classList.remove('sent');
                }, 2000);
            }
        }
    } catch (e) {
        console.error('Failed to send quick phrase:', e);
    }
}

async function addQuickPhrase() {
    const input = document.getElementById('new_phrase_input');
    const text = input?.value.trim();
    
    if (!text) return;
    
    try {
        const response = await fetch('/add_quick_phrase', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, emoji: '', category: 'custom' })
        });
        
        if (response.ok) {
            const data = await response.json();
            input.value = '';
            refreshQuickPhrases(data.phrases);
        }
    } catch (e) {
        console.error('Failed to add quick phrase:', e);
    }
}

function refreshQuickPhrases(phrases) {
    const list = document.getElementById('quick_phrases_list');
    if (!list) return;
    
    list.innerHTML = phrases.map(p => 
        `<button type="button" class="quick-phrase-btn" data-phrase="${p.text.replace(/"/g, '&quot;')}" title="Click to send">
            ${p.emoji ? p.emoji + ' ' : ''}${p.text.length > 20 ? p.text.substring(0, 20) + '...' : p.text}
        </button>`
    ).join('');
    
    document.querySelectorAll('.quick-phrase-btn').forEach(btn => {
        btn.addEventListener('click', () => sendQuickPhrase(btn.dataset.phrase));
    });
}

function setupAfkTracking() {
    let afkActivityTimer = null;
    
    const reportActivity = () => {
        if (afkActivityTimer) clearTimeout(afkActivityTimer);
        afkActivityTimer = setTimeout(() => {
            fetch('/afk_activity', { method: 'POST' }).catch(() => {});
        }, 1000);
    };
    
    document.addEventListener('mousemove', reportActivity);
    document.addEventListener('keydown', reportActivity);
    document.addEventListener('click', reportActivity);
    document.addEventListener('scroll', reportActivity);
}

function setupBodyTracking() {
    const startCliBtn = document.getElementById('btn_fbt_start_cli');
    const recenterBtn = document.getElementById('btn_fbt_recenter');
    const stopBtn = document.getElementById('btn_fbt_stop');
    const saveBtn = document.getElementById('btn_fbt_save_settings');
    const startRouterBtn = document.getElementById('btn_router_start');
    const stopRouterBtn = document.getElementById('btn_router_stop');
    const secondaryEnabledCheckbox = document.getElementById('fbt_secondary_enabled');
    const fbtFields = document.querySelectorAll('[id^="fbt_"]');

    const postJson = async (url, body = null) => {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body ? JSON.stringify(body) : null
        });
        let payload = {};
        try {
            payload = await response.json();
        } catch (_) {
            payload = {};
        }
        if (!response.ok && payload.error) {
            alert(payload.error);
        }
        return payload;
    };

    startCliBtn?.addEventListener('click', async () => {
        await saveFbtSettings(postJson, true);
        await postJson('/fbt/start', { mode: 'gui' });
        await updateStatus();
    });

    recenterBtn?.addEventListener('click', async () => {
        const res = await postJson('/fbt/recenter');
        if (!res || res.ok !== false) {
            startFbtRecenterCountdown(5.0);
        }
        await updateStatus();
    });

    stopBtn?.addEventListener('click', async () => {
        await postJson('/fbt/stop');
        await updateStatus();
    });

    saveBtn?.addEventListener('click', async () => {
        await saveFbtSettings(postJson, false);
        await updateStatus();
    });

    startRouterBtn?.addEventListener('click', async () => {
        const listenIp = document.getElementById('router_listen_ip')?.value?.trim() || '127.0.0.1';
        const listenPort = parseInt(document.getElementById('router_listen_port')?.value || '9010', 10);
        await postJson('/osc-router/start', { listen_ip: listenIp, listen_port: listenPort });
        await updateStatus();
    });

    stopRouterBtn?.addEventListener('click', async () => {
        await postJson('/osc-router/stop');
        await updateStatus();
    });

    secondaryEnabledCheckbox?.addEventListener('change', updateSecondaryUiState);
    fbtFields.forEach((el) => {
        el.addEventListener('input', () => { fbtSettingsDirty = true; });
        el.addEventListener('change', () => { fbtSettingsDirty = true; });
    });
    updateSecondaryUiState();
}

function setFbtRecenterCountdownView(secondsLeft) {
    const badge = document.getElementById('fbt_recenter_countdown');
    if (!badge) return;
    if (secondsLeft <= 0) {
        badge.style.display = 'none';
        badge.textContent = '';
        badge.classList.remove('status-on');
        badge.classList.add('status-off');
        return;
    }
    badge.style.display = 'inline-flex';
    badge.classList.remove('status-off');
    badge.classList.add('status-on');
    badge.textContent = `Recenter in ${secondsLeft.toFixed(1)}s`;
}

function playFbtBeep() {
    try {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return;
        const ctx = new Ctx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.value = 880;
        gain.gain.value = 0.05;
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        setTimeout(() => {
            try { osc.stop(); } catch (_) {}
            try { ctx.close(); } catch (_) {}
        }, 140);
    } catch (_) {
        // Ignore audio failures; visual countdown still works.
    }
}

function startFbtRecenterCountdown(seconds) {
    fbtRecenterEndsAt = Date.now() + Math.max(0, seconds) * 1000;
    if (fbtRecenterTimer) {
        clearInterval(fbtRecenterTimer);
        fbtRecenterTimer = null;
    }
    const tick = () => {
        const left = Math.max(0, (fbtRecenterEndsAt - Date.now()) / 1000);
        setFbtRecenterCountdownView(left);
        if (left <= 0) {
            if (fbtRecenterTimer) {
                clearInterval(fbtRecenterTimer);
                fbtRecenterTimer = null;
            }
            playFbtBeep();
        }
    };
    tick();
    fbtRecenterTimer = setInterval(tick, 100);
}

async function saveFbtSettings(postJsonFn, silent = false) {
    const postJson = postJsonFn || (async (url, body) => {
        const r = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        return r.json();
    });

    const numberValue = (id, fallback = 0) => {
        const v = parseFloat(document.getElementById(id)?.value || '');
        return Number.isFinite(v) ? v : fallback;
    };

    const intValue = (id, fallback = 0) => {
        const v = parseInt(document.getElementById(id)?.value || '', 10);
        return Number.isFinite(v) ? v : fallback;
    };

    const body = {
        mode: document.getElementById('fbt_mode')?.value || 'vrchat_trackers',
        camera_source: document.getElementById('fbt_camera_source')?.value || 'local',
        phone_camera_url: document.getElementById('fbt_phone_camera_url')?.value || '',
        camera: intValue('fbt_camera', 0),
        smoothing: numberValue('fbt_smoothing', 0.4),
        position_scale: numberValue('fbt_position_scale', 1),
        height_m: numberValue('fbt_height_m', 1.65),
        floor_offset_m: numberValue('fbt_floor_offset_m', 0),
        hips_offset_m: numberValue('fbt_hips_offset_m', 0),
        feet_y_offset_m: numberValue('fbt_feet_y_offset_m', -0.02),
        lower_body_y_offset_m: numberValue('fbt_lower_body_y_offset_m', 0),
        x_offset_m: numberValue('fbt_x_offset_m', 0),
        z_offset_m: numberValue('fbt_z_offset_m', 0),
        send_rate: numberValue('fbt_send_rate', 60),
        preview_fps: numberValue('fbt_preview_fps', 30),
        foot_yaw_blend: numberValue('fbt_foot_yaw_blend', 0.78),
        foot_yaw_offset_deg: numberValue('fbt_foot_yaw_offset_deg', 0),
        mirror: !!document.getElementById('fbt_mirror')?.checked,
        show_overlay: !!document.getElementById('fbt_show_overlay')?.checked,
        send_head_align: !!document.getElementById('fbt_send_head_align')?.checked,
        send_chest_tracker: !!document.getElementById('fbt_send_chest_tracker')?.checked,
        send_knee_trackers: !!document.getElementById('fbt_send_knee_trackers')?.checked,
        send_elbow_trackers: !!document.getElementById('fbt_send_elbow_trackers')?.checked,
        estimation_enabled: !!document.getElementById('fbt_estimation_enabled')?.checked,
        estimation_strength: numberValue('fbt_estimation_strength', 0.82),
        occlusion_confidence_threshold: numberValue('fbt_occlusion_confidence_threshold', 0.45),
        occlusion_velocity_damping: numberValue('fbt_occlusion_velocity_damping', 0.86),
        secondary_enabled: !!document.getElementById('fbt_secondary_enabled')?.checked,
        secondary_source: document.getElementById('fbt_secondary_source')?.value || 'phone',
        secondary_phone_camera_url: document.getElementById('fbt_secondary_phone_camera_url')?.value || '',
        secondary_camera: intValue('fbt_secondary_camera', 1),
        secondary_blend: numberValue('fbt_secondary_blend', 0.35),
        secondary_target: document.getElementById('fbt_secondary_target')?.value || 'lower_body',
        secondary_rotation: document.getElementById('fbt_secondary_rotation')?.value || '90cw',
        secondary_mount_preset: document.getElementById('fbt_secondary_mount_preset')?.value || 'right',
        secondary_yaw_deg: numberValue('fbt_secondary_yaw_deg', 0),
        secondary_pitch_deg: numberValue('fbt_secondary_pitch_deg', 0)
    };

    const res = await postJson('/fbt/settings', body);
    if (!silent && res && res.ok) {
        alert('Tracker settings saved');
    }
    if (res && res.ok && res.settings) {
        fbtSettingsDirty = false;
        applyFbtSettings(res.settings);
        fbtSettingsHydrated = true;
    }
}

function applyFbtSettings(settings) {
    if (!settings) return;
    const setVal = (id, value) => {
        const el = document.getElementById(id);
        if (el && value !== undefined && value !== null) el.value = String(value);
    };
    const setCheck = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.checked = !!value;
    };
    setVal('fbt_mode', settings.mode);
    setVal('fbt_camera_source', settings.camera_source);
    setVal('fbt_phone_camera_url', settings.phone_camera_url);
    setVal('fbt_camera', settings.camera);
    setVal('fbt_smoothing', settings.smoothing);
    setVal('fbt_position_scale', settings.position_scale);
    setVal('fbt_height_m', settings.height_m);
    setVal('fbt_floor_offset_m', settings.floor_offset_m);
    setVal('fbt_hips_offset_m', settings.hips_offset_m);
    setVal('fbt_feet_y_offset_m', settings.feet_y_offset_m);
    setVal('fbt_lower_body_y_offset_m', settings.lower_body_y_offset_m);
    setVal('fbt_x_offset_m', settings.x_offset_m);
    setVal('fbt_z_offset_m', settings.z_offset_m);
    setVal('fbt_send_rate', settings.send_rate);
    setVal('fbt_preview_fps', settings.preview_fps);
    setVal('fbt_foot_yaw_blend', settings.foot_yaw_blend);
    setVal('fbt_foot_yaw_offset_deg', settings.foot_yaw_offset_deg);
    setCheck('fbt_mirror', settings.mirror);
    setCheck('fbt_show_overlay', settings.show_overlay);
    setCheck('fbt_send_head_align', settings.send_head_align);
    setCheck('fbt_send_chest_tracker', settings.send_chest_tracker);
    setCheck('fbt_send_knee_trackers', settings.send_knee_trackers);
    setCheck('fbt_send_elbow_trackers', settings.send_elbow_trackers);
    setCheck('fbt_estimation_enabled', settings.estimation_enabled);
    setVal('fbt_estimation_strength', settings.estimation_strength);
    setVal('fbt_occlusion_confidence_threshold', settings.occlusion_confidence_threshold);
    setVal('fbt_occlusion_velocity_damping', settings.occlusion_velocity_damping);
    setCheck('fbt_secondary_enabled', settings.secondary_enabled);
    setVal('fbt_secondary_source', settings.secondary_source);
    setVal('fbt_secondary_phone_camera_url', settings.secondary_phone_camera_url);
    setVal('fbt_secondary_camera', settings.secondary_camera);
    setVal('fbt_secondary_blend', settings.secondary_blend);
    setVal('fbt_secondary_target', settings.secondary_target);
    setVal('fbt_secondary_rotation', settings.secondary_rotation);
    setVal('fbt_secondary_mount_preset', settings.secondary_mount_preset);
    setVal('fbt_secondary_yaw_deg', settings.secondary_yaw_deg);
    setVal('fbt_secondary_pitch_deg', settings.secondary_pitch_deg);
    updateSecondaryUiState();
}

function updateSecondaryUiState() {
    const enabled = !!document.getElementById('fbt_secondary_enabled')?.checked;
    const ids = [
        'fbt_secondary_source',
        'fbt_secondary_camera',
        'fbt_secondary_phone_camera_url',
        'fbt_secondary_blend',
        'fbt_secondary_target',
        'fbt_secondary_rotation',
        'fbt_secondary_mount_preset',
        'fbt_secondary_yaw_deg',
        'fbt_secondary_pitch_deg'
    ];
    ids.forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.disabled = !enabled;
        el.style.opacity = enabled ? '1' : '0.6';
    });
}

async function toggleSystemStats() {
    try {
        const response = await fetch('/toggle_system_stats', { method: 'POST' });
        const data = await response.json();
        
        const btn = document.getElementById('btn_system_stats');
        if (btn) {
            btn.classList.toggle('btn-on', data.enabled);
            btn.classList.toggle('btn-off', !data.enabled);
        }
        
        const statsLine = document.getElementById('system_stats_line');
        if (statsLine) {
            statsLine.style.display = data.enabled ? 'block' : 'none';
        }
    } catch (e) {
        console.error('Failed to toggle system stats:', e);
    }
}

async function toggleAfk() {
    try {
        const response = await fetch('/toggle_afk', { method: 'POST' });
        const data = await response.json();
        
        const btn = document.getElementById('btn_afk');
        if (btn) {
            btn.classList.toggle('btn-on', data.enabled);
            btn.classList.toggle('btn-off', !data.enabled);
        }
        
        const afkLine = document.getElementById('afk_status_line');
        if (afkLine) {
            afkLine.style.display = data.enabled ? 'block' : 'none';
        }
    } catch (e) {
        console.error('Failed to toggle AFK:', e);
    }
}

function setupTabs() {
    document.getElementById('chatbox_main_tab')?.addEventListener('click', () => showMainTab('chatbox'));
    document.getElementById('body_tracking_main_tab')?.addEventListener('click', () => showMainTab('body_tracking'));
    document.getElementById('router_main_tab')?.addEventListener('click', () => showMainTab('router'));
    document.getElementById('vrcx_plus_main_tab')?.addEventListener('click', () => showMainTab('vrcx_plus'));
    document.getElementById('dashboard_tab')?.addEventListener('click', () => showChatboxSubtab('dashboard'));
    document.getElementById('settings_tab')?.addEventListener('click', () => showChatboxSubtab('settings'));
    document.getElementById('advanced_tab')?.addEventListener('click', () => showChatboxSubtab('advanced'));
    showMainTab('chatbox');
    showChatboxSubtab('dashboard');
}

function showMainTab(tab) {
    document.getElementById('chatbox_main_tab')?.classList.toggle('active', tab === 'chatbox');
    document.getElementById('body_tracking_main_tab')?.classList.toggle('active', tab === 'body_tracking');
    document.getElementById('router_main_tab')?.classList.toggle('active', tab === 'router');
    document.getElementById('vrcx_plus_main_tab')?.classList.toggle('active', tab === 'vrcx_plus');
    const chatboxSubtabs = document.getElementById('chatbox_subtabs');
    if (chatboxSubtabs) chatboxSubtabs.style.display = tab === 'chatbox' ? 'flex' : 'none';

    if (tab === 'chatbox') {
        const activeSubtab = document.getElementById('settings_tab')?.classList.contains('active')
            ? 'settings'
            : (document.getElementById('advanced_tab')?.classList.contains('active') ? 'advanced' : 'dashboard');
        showChatboxSubtab(activeSubtab);
    } else {
        document.getElementById('dashboard_content').style.display = 'none';
        document.getElementById('settings_content').style.display = 'none';
        document.getElementById('advanced_content').style.display = 'none';
        document.getElementById('body_tracking_content').style.display = tab === 'body_tracking' ? 'block' : 'none';
        document.getElementById('router_content').style.display = tab === 'router' ? 'block' : 'none';
        document.getElementById('vrcx_plus_content').style.display = tab === 'vrcx_plus' ? 'block' : 'none';
        if (tab === 'vrcx_plus') {
            refreshVrcxPlusState();
        }
    }
}

function showChatboxSubtab(tab) {
    document.getElementById('chatbox_main_tab')?.classList.add('active');
    document.getElementById('body_tracking_main_tab')?.classList.remove('active');
    document.getElementById('router_main_tab')?.classList.remove('active');
    document.getElementById('vrcx_plus_main_tab')?.classList.remove('active');
    const chatboxSubtabs = document.getElementById('chatbox_subtabs');
    if (chatboxSubtabs) chatboxSubtabs.style.display = 'flex';
    document.getElementById('dashboard_tab')?.classList.toggle('active', tab === 'dashboard');
    document.getElementById('settings_tab')?.classList.toggle('active', tab === 'settings');
    document.getElementById('advanced_tab')?.classList.toggle('active', tab === 'advanced');
    document.getElementById('dashboard_content').style.display = tab === 'dashboard' ? 'block' : 'none';
    document.getElementById('settings_content').style.display = tab === 'settings' ? 'block' : 'none';
    document.getElementById('advanced_content').style.display = tab === 'advanced' ? 'block' : 'none';
    document.getElementById('body_tracking_content').style.display = 'none';
    document.getElementById('router_content').style.display = 'none';
    document.getElementById('vrcx_plus_content').style.display = 'none';
    if (tab === 'settings') {
        loadCustomMessages();
    } else if (tab === 'advanced') {
        loadPerMessageTimings();
        loadMessageWeights();
    }
}

function showTab(tab) {
    if (tab === 'body_tracking') return showMainTab('body_tracking');
    if (tab === 'router') return showMainTab('router');
    if (tab === 'vrcx_plus') return showMainTab('vrcx_plus');
    return showChatboxSubtab(tab);
}

function setupVrcxPlus() {
    if (vrcxPlusInitialized) return;
    vrcxPlusInitialized = true;

    document.getElementById('btn_vrcx_plus_search')?.addEventListener('click', () => runVrcxPlusSearch());
    document.getElementById('btn_vrcx_plus_reset')?.addEventListener('click', () => resetVrcxPlusFilters());
    document.getElementById('btn_vrcx_plus_add')?.addEventListener('click', () => addVrcxPlusItem());
    document.getElementById('btn_vrcx_plus_add_note')?.addEventListener('click', () => addVrcxPlusNote());
    document.getElementById('btn_vrcx_plus_add_event')?.addEventListener('click', () => addVrcxPlusEvent());
    document.getElementById('btn_vrcx_plus_vrchat_login')?.addEventListener('click', () => loginVrcxPlusVrchat());
    document.getElementById('btn_vrcx_plus_vrchat_logout')?.addEventListener('click', () => logoutVrcxPlusVrchat());
    document.getElementById('btn_vrcx_plus_vrchat_2fa')?.addEventListener('click', () => verifyVrcxPlusVrchat2fa());
    document.getElementById('btn_vrcx_plus_vrchat_email_otp')?.addEventListener('click', () => requestVrcxPlusVrchatEmailOtp());
    document.getElementById('btn_vrcx_plus_vrchat_avatar_search')?.addEventListener('click', () => searchVrcxPlusVrchatAvatars());
    document.getElementById('btn_vrcx_plus_vrchat_snapshot')?.addEventListener('click', () => captureVrcxPlusFriendSnapshot());
    document.getElementById('btn_vrcx_plus_provider_save')?.addEventListener('click', () => saveVrcxPlusProvider());
    document.getElementById('btn_vrcx_plus_auto_snapshot_save')?.addEventListener('click', () => saveVrcxPlusAutoSnapshot());
    document.getElementById('vrcx_plus_subtab_overview')?.addEventListener('click', () => showVrcxPlusSubtab('overview'));
    document.getElementById('vrcx_plus_subtab_search')?.addEventListener('click', () => showVrcxPlusSubtab('search'));
    document.getElementById('vrcx_plus_subtab_vrchat')?.addEventListener('click', () => showVrcxPlusSubtab('vrchat'));
    document.getElementById('vrcx_plus_subtab_logs')?.addEventListener('click', () => showVrcxPlusSubtab('logs'));
    document.getElementById('vrcx_plus_query')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') runVrcxPlusSearch();
    });
    document.getElementById('vrcx_plus_vrchat_avatar_query')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') searchVrcxPlusVrchatAvatars();
    });
    document.getElementById('vrcx_plus_history_user_filter')?.addEventListener('input', () => scheduleVrcxPlusHistoryRefresh());
    document.getElementById('vrcx_plus_history_recent_filter')?.addEventListener('change', () => {
        vrcxPlusHistorySelectedUserId = '';
        refreshVrcxPlusHistoryUsers();
        refreshVrcxPlusAvatarHistory();
    });
    document.getElementById('vrcx_plus_avatar_history_query')?.addEventListener('input', () => scheduleVrcxPlusAvatarHistoryRefresh());
    document.getElementById('vrcx_plus_avatar_history_recent')?.addEventListener('change', () => refreshVrcxPlusAvatarHistory());
    document.getElementById('vrcx_plus_avatar_history_selected_only')?.addEventListener('change', () => refreshVrcxPlusAvatarHistory());

    showVrcxPlusSubtab('overview');
    refreshVrcxPlusState();
}

function showVrcxPlusSubtab(tab) {
    const tabIds = ['overview', 'search', 'vrchat', 'logs'];
    tabIds.forEach((id) => {
        const btn = document.getElementById(`vrcx_plus_subtab_${id}`);
        const panel = document.getElementById(`vrcx_plus_panel_${id}`);
        if (btn) btn.classList.toggle('active', id === tab);
        if (panel) panel.style.display = id === tab ? 'block' : 'none';
    });
}

function setVrcxPlusStatus(text, isOn = false) {
    const badge = document.getElementById('vrcx_plus_status_badge');
    if (!badge) return;
    badge.textContent = text;
    badge.classList.toggle('status-on', !!isOn);
    badge.classList.toggle('status-off', !isOn);
}

async function vrcxPlusPost(url, body = null) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : null
    });
    let payload = {};
    try {
        payload = await response.json();
    } catch (_) {
        payload = {};
    }
    if (!response.ok) {
        const msg = payload?.error || `Request failed (${response.status})`;
        throw new Error(msg);
    }
    return payload;
}

async function refreshVrcxPlusState() {
    try {
        setVrcxPlusStatus('Loading...');
        const response = await fetch('/vrcx-plus/state');
        const payload = await response.json();
        if (!payload?.ok) {
            throw new Error(payload?.error || 'Failed to load VRCX+ state');
        }
        vrcxPlusData = payload.data || {};
        renderVrcxPlusStats(payload.stats || {});
        renderVrcxPlusNotes(vrcxPlusData.notes || []);
        renderVrcxPlusEvents(vrcxPlusData.events || []);
        renderVrcxPlusFriendLogs(vrcxPlusData.friend_logs || []);
        renderVrcxPlusVrchatAuth(payload.vrchat || {});
        renderVrcxPlusProvider(payload.provider || {});
        renderVrcxPlusAutoSnapshot(payload.auto_snapshot || {});
        await refreshVrcxPlusHistoryUsers();
        await refreshVrcxPlusAvatarHistory();
        await runVrcxPlusSearch(false);
        setVrcxPlusStatus('Ready', true);
    } catch (e) {
        console.error('VRCX+ state error:', e);
        setVrcxPlusStatus('Error');
    }
}

function renderVrcxPlusStats(stats) {
    const total = stats.total_items || 0;
    const favCount =
        (stats.favorite_avatars || 0) +
        (stats.favorite_worlds || 0) +
        (stats.favorite_friends || 0);
    const setText = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    };
    setText('vrcx_plus_stat_total', `Items: ${total}`);
    setText('vrcx_plus_stat_avatar', `Avatars: ${stats.avatars || 0}`);
    setText('vrcx_plus_stat_world', `Worlds: ${stats.worlds || 0}`);
    setText('vrcx_plus_stat_friend', `Friends: ${stats.friends || 0}`);
    setText('vrcx_plus_stat_fav', `Favorites: ${favCount}`);
}

function renderVrcxPlusNotes(notes) {
    const wrap = document.getElementById('vrcx_plus_notes');
    if (!wrap) return;
    if (!notes.length) {
        wrap.textContent = 'No notes yet.';
        return;
    }
    wrap.innerHTML = notes
        .slice(0, 50)
        .map((note) => `<div class="vrcx-plus-item"><span>${escapeHtml(note.text || '')}</span><small>${escapeHtml(note.created_at || '')}</small></div>`)
        .join('');
}

function renderVrcxPlusEvents(events) {
    const wrap = document.getElementById('vrcx_plus_events');
    if (!wrap) return;
    if (!events.length) {
        wrap.textContent = 'No events yet.';
        return;
    }
    wrap.innerHTML = events
        .slice(0, 80)
        .map(
            (event) =>
                `<div class="vrcx-plus-item"><span><strong>${escapeHtml(event.kind || 'event')}</strong> ${escapeHtml(event.title || '')}<br><small>${escapeHtml(event.detail || '')}</small></span><small>${escapeHtml(event.created_at || '')}</small></div>`
        )
        .join('');
}

function renderVrcxPlusFriendLogs(logs) {
    const wrap = document.getElementById('vrcx_plus_friend_logs');
    if (!wrap) return;
    if (!logs.length) {
        wrap.textContent = 'No snapshots yet.';
        return;
    }
    wrap.innerHTML = logs
        .slice(0, 20)
        .map((entry) => {
            const friendButtons = (entry.friends || [])
                .slice(0, 6)
                .map((f) => {
                    const fid = f.id || '';
                    const name = f.displayName || 'Unknown';
                    if (!fid) return '';
                    return `<button type="button" class="btn-off" onclick="loadVrcxPlusFriendHistory('${escapeJs(fid)}')">${escapeHtml(name)}</button>`;
                })
                .join('');
            return `<div class="vrcx-plus-item"><span><strong>${escapeHtml(entry.created_at || '')}</strong><br><small>${entry.count || 0} friends | ${escapeHtml(entry.source || 'manual')}</small></span><span class="vrcx-plus-actions">${friendButtons || '<small>No entries</small>'}</span></div>`;
        })
        .join('');
}

function renderVrcxPlusVrchatAuth(vrchat) {
    const badge = document.getElementById('vrcx_plus_vrchat_auth_badge');
    const text = document.getElementById('vrcx_plus_vrchat_auth_text');
    if (!badge || !text) return;
    const loggedIn = !!vrchat?.logged_in;
    const requires2fa = !!vrchat?.requires_2fa;
    const methods = Array.isArray(vrchat?.methods)
        ? vrchat.methods.map((method) => String(method || '').trim()).filter(Boolean)
        : [];
    vrcxPlusVrchatStatus = { loggedIn, requires2fa, methods };

    if (loggedIn) {
        const user = vrchat?.user || {};
        badge.textContent = 'Logged in';
        badge.classList.toggle('status-on', true);
        badge.classList.toggle('status-off', false);
        text.textContent = `${user.displayName || user.username || user.id || 'VRChat user'}`;
        text.style.color = '';
        return;
    }

    badge.textContent = requires2fa ? '2FA required' : 'Logged out';
    badge.classList.toggle('status-on', false);
    badge.classList.toggle('status-off', true);

    if (requires2fa) {
        const methodText = methods.length ? methods.join(', ') : 'totp/emailOtp';
        text.textContent = `Verify ${methodText} code to finish login.`;
        text.style.color = '#ffcc66';
        return;
    }

    const errorText = String(vrchat?.error || '').trim();
    text.textContent = errorText ? `Error: ${errorText}` : 'Log in to use VRChat actions.';
    text.style.color = errorText ? '#ff8b8b' : '#999';
}

function isVrcxPlusAuthErrorMessage(message) {
    const value = String(message || '').toLowerCase();
    return (
        value.includes('401') ||
        value.includes('unauthorized') ||
        value.includes('two-factor') ||
        value.includes('two factor') ||
        value.includes('authorization required') ||
        value.includes('2fa required') ||
        value.includes('verify 2fa')
    );
}

function ensureVrcxPlusVrchatReady(featureLabel) {
    if (vrcxPlusVrchatStatus.loggedIn) return true;

    showVrcxPlusSubtab('vrchat');
    const methods = Array.isArray(vrcxPlusVrchatStatus.methods) ? vrcxPlusVrchatStatus.methods : [];
    const methodText = methods.length ? methods.join(', ') : 'totp/emailOtp';
    const action = featureLabel || 'this action';
    if (vrcxPlusVrchatStatus.requires2fa) {
        setVrcxPlusAuthText(`2FA pending (${methodText}). Verify 2FA to use ${action}.`, true);
        alert(`VRChat 2FA is required before ${action}.`);
    } else {
        setVrcxPlusAuthText(`VRChat login required for ${action}.`, true);
        alert(`Please log in to VRChat before ${action}.`);
    }
    setVrcxPlusStatus('VRChat auth required');
    return false;
}

function setVrcxPlusAuthText(message, isError = false) {
    const text = document.getElementById('vrcx_plus_vrchat_auth_text');
    if (!text) return;
    text.textContent = message || '';
    text.style.color = isError ? '#ff8b8b' : '';
}

function setVrcxPlusAuthBusy(buttonId, busy, busyLabel, idleLabel) {
    const btn = document.getElementById(buttonId);
    if (!btn) return;
    btn.disabled = !!busy;
    if (busy) {
        btn.dataset.idleLabel = btn.dataset.idleLabel || btn.textContent || '';
        btn.textContent = busyLabel || 'Working...';
    } else {
        btn.textContent = idleLabel || btn.dataset.idleLabel || btn.textContent;
    }
}

function normalizeVrcxPlusProviderUrls(rawValue) {
    if (Array.isArray(rawValue)) {
        const merged = [];
        rawValue.forEach((entry) => {
            normalizeVrcxPlusProviderUrls(entry).forEach((url) => merged.push(url));
        });
        const seen = new Set();
        return merged.filter((url) => {
            if (!url || seen.has(url)) return false;
            seen.add(url);
            return true;
        });
    }
    const text = String(rawValue || '');
    const seen = new Set();
    const parts = [];
    text.replace(/\r/g, '\n')
        .split('\n')
        .forEach((line) => {
            line.split(/[;,]/g).forEach((entry) => parts.push(entry));
        });
    return parts
        .map((entry) => entry.trim())
        .filter((entry) => {
            if (!entry || seen.has(entry)) return false;
            seen.add(entry);
            return true;
        });
}

function getVrcxPlusProviderUrlsInput() {
    const urlsEl = document.getElementById('vrcx_plus_provider_urls');
    if (urlsEl) return normalizeVrcxPlusProviderUrls(urlsEl.value || '');
    const legacyEl = document.getElementById('vrcx_plus_provider_url');
    if (legacyEl) return normalizeVrcxPlusProviderUrls(legacyEl.value || '');
    return [];
}

function setVrcxPlusProviderUrlsInput(urls) {
    const normalized = normalizeVrcxPlusProviderUrls(urls);
    const urlsEl = document.getElementById('vrcx_plus_provider_urls');
    if (urlsEl) urlsEl.value = normalized.join('\n');
    const legacyEl = document.getElementById('vrcx_plus_provider_url');
    if (legacyEl) legacyEl.value = normalized[0] || '';
}

function renderVrcxPlusProvider(provider) {
    const enabledEl = document.getElementById('vrcx_plus_provider_enabled');
    if (enabledEl) enabledEl.checked = !!provider?.enabled;
    const urls = normalizeVrcxPlusProviderUrls(provider?.urls || provider?.url || '');
    setVrcxPlusProviderUrlsInput(urls);
}

function renderVrcxPlusAutoSnapshot(config) {
    const enabledEl = document.getElementById('vrcx_plus_auto_snapshot_enabled');
    const minutesEl = document.getElementById('vrcx_plus_auto_snapshot_minutes');
    const includeOfflineEl = document.getElementById('vrcx_plus_auto_snapshot_include_offline');
    if (enabledEl) enabledEl.checked = !!config?.enabled;
    if (minutesEl && config?.minutes !== undefined) minutesEl.value = String(config.minutes || 10);
    if (includeOfflineEl) includeOfflineEl.checked = !!config?.include_offline;
}

function getVrcxPlusSearchFilters() {
    return {
        query: document.getElementById('vrcx_plus_query')?.value || '',
        type: document.getElementById('vrcx_plus_type')?.value || 'all',
        status: document.getElementById('vrcx_plus_status')?.value || 'all',
        sort: document.getElementById('vrcx_plus_sort')?.value || 'updated',
        author: document.getElementById('vrcx_plus_author')?.value || '',
        favorites_only: !!document.getElementById('vrcx_plus_favorites_only')?.checked
    };
}

async function runVrcxPlusSearch(updateState = true) {
    try {
        setVrcxPlusStatus('Searching...');
        const payload = await vrcxPlusPost('/vrcx-plus/search', getVrcxPlusSearchFilters());
        renderVrcxPlusResults(payload.results || []);
        if (updateState) {
            setVrcxPlusStatus('Ready', true);
        }
    } catch (e) {
        console.error('VRCX+ search error:', e);
        setVrcxPlusStatus('Search failed');
    }
}

function renderVrcxPlusResults(results) {
    const wrap = document.getElementById('vrcx_plus_results');
    if (!wrap) return;
    if (!results.length) {
        wrap.textContent = 'No results found.';
        return;
    }
    wrap.innerHTML = results
        .map((item) => {
            const isFav = isVrcxPlusFavorite(item);
            const avatarId = item.external_id || item.id || '';
            const canWear = (item.type || '') === 'avatar' && String(avatarId).startsWith('avtr_');
            return `
                <div class="vrcx-plus-item">
                    <span>
                        <strong>[${escapeHtml(item.type || '?')}]</strong> ${escapeHtml(item.name || '')}
                        <br><small>${escapeHtml(item.author || '')} ${escapeHtml(item.status || '')}</small>
                        ${avatarId ? `<br><small>ID: ${escapeHtml(avatarId)}</small>` : ''}
                        <br><small>${escapeHtml(item.description || '')}</small>
                    </span>
                    <span class="vrcx-plus-actions">
                        ${canWear ? `<button type="button" class="btn-on" onclick="wearVrchatAvatar('${escapeJs(avatarId)}')">Wear</button>` : ''}
                        <button type="button" class="${isFav ? 'btn-on' : 'btn-off'}" onclick="toggleVrcxPlusFavorite('${escapeJs(item.id)}','${escapeJs(item.type)}')">${isFav ? '★' : '☆'}</button>
                        <button type="button" class="btn-off" onclick="deleteVrcxPlusItem('${escapeJs(item.id)}')">Delete</button>
                    </span>
                </div>
            `;
        })
        .join('');
}

function isVrcxPlusFavorite(item) {
    if (!vrcxPlusData || !item) return false;
    const type = (item.type || '').toLowerCase();
    const list = vrcxPlusData?.favorites?.[type] || [];
    return list.includes(item.id);
}

async function addVrcxPlusItem() {
    const type = document.getElementById('vrcx_plus_add_type')?.value || 'avatar';
    const name = document.getElementById('vrcx_plus_add_name')?.value?.trim() || '';
    const author = document.getElementById('vrcx_plus_add_author')?.value?.trim() || '';
    const description = document.getElementById('vrcx_plus_add_description')?.value?.trim() || '';
    const status = document.getElementById('vrcx_plus_add_status')?.value || 'public';
    if (!name) {
        alert('Please enter a name.');
        return;
    }
    try {
        await vrcxPlusPost('/vrcx-plus/item', { type, name, author, description, status });
        document.getElementById('vrcx_plus_add_name').value = '';
        document.getElementById('vrcx_plus_add_author').value = '';
        document.getElementById('vrcx_plus_add_description').value = '';
        await refreshVrcxPlusState();
    } catch (e) {
        alert(`Failed to add item: ${e.message}`);
    }
}

async function deleteVrcxPlusItem(itemId) {
    if (!itemId) return;
    if (!confirm('Delete this item?')) return;
    try {
        await vrcxPlusPost('/vrcx-plus/item/delete', { id: itemId });
        await refreshVrcxPlusState();
    } catch (e) {
        alert(`Failed to delete item: ${e.message}`);
    }
}

async function toggleVrcxPlusFavorite(itemId, itemType) {
    if (!itemId || !itemType) return;
    try {
        await vrcxPlusPost('/vrcx-plus/favorite/toggle', { id: itemId, type: itemType });
        await refreshVrcxPlusState();
    } catch (e) {
        alert(`Failed to toggle favorite: ${e.message}`);
    }
}

async function addVrcxPlusNote() {
    const input = document.getElementById('vrcx_plus_note_text');
    const text = input?.value?.trim() || '';
    if (!text) return;
    try {
        await vrcxPlusPost('/vrcx-plus/note', { text });
        input.value = '';
        await refreshVrcxPlusState();
    } catch (e) {
        alert(`Failed to add note: ${e.message}`);
    }
}

async function addVrcxPlusEvent() {
    const kind = document.getElementById('vrcx_plus_event_kind')?.value || 'notification';
    const title = document.getElementById('vrcx_plus_event_title')?.value?.trim() || '';
    const detail = document.getElementById('vrcx_plus_event_detail')?.value?.trim() || '';
    if (!title) {
        alert('Event title is required.');
        return;
    }
    try {
        await vrcxPlusPost('/vrcx-plus/event', { kind, title, detail });
        document.getElementById('vrcx_plus_event_title').value = '';
        document.getElementById('vrcx_plus_event_detail').value = '';
        await refreshVrcxPlusState();
    } catch (e) {
        alert(`Failed to add event: ${e.message}`);
    }
}

async function loginVrcxPlusVrchat() {
    const username = document.getElementById('vrcx_plus_vrchat_username')?.value?.trim() || '';
    const password = document.getElementById('vrcx_plus_vrchat_password')?.value || '';
    if (!username || !password) {
        setVrcxPlusAuthText('Enter VRChat username and password.', true);
        return;
    }
    try {
        setVrcxPlusAuthBusy('btn_vrcx_plus_vrchat_login', true, 'Logging in...', 'Login');
        setVrcxPlusStatus('Logging in VRChat...');
        setVrcxPlusAuthText('Signing in to VRChat...', false);
        const payload = await vrcxPlusPost('/vrcx-plus/vrchat/login', { username, password });
        if (payload.requires_2fa) {
            const methods = Array.isArray(payload.methods)
                ? payload.methods
                : (payload.methods ? [String(payload.methods)] : []);
            const methodNames = methods.join(', ') || 'totp/emailOtp';
            const methodSelect = document.getElementById('vrcx_plus_vrchat_2fa_method');
            if (methodSelect && methods.length) {
                if (methods.some((m) => String(m).toLowerCase() === 'emailotp')) {
                    methodSelect.value = 'emailOtp';
                } else if (methods.some((m) => String(m).toLowerCase() === 'otp')) {
                    methodSelect.value = 'otp';
                } else {
                    methodSelect.value = 'totp';
                }
            }
            if (payload.email_otp_sent) {
                setVrcxPlusAuthText(`2FA required (${methodNames}). Email code sent.`, false);
            } else {
                const emailErr = payload.email_otp_error ? ` Email OTP: ${payload.email_otp_error}` : '';
                setVrcxPlusAuthText(`2FA required (${methodNames}).${emailErr}`, true);
            }
        } else if (payload.logged_in) {
            setVrcxPlusAuthText('Logged in successfully.', false);
        }
        await refreshVrcxPlusState();
    } catch (e) {
        setVrcxPlusAuthText(`VRChat login failed: ${e.message}`, true);
        setVrcxPlusStatus('Error');
    } finally {
        setVrcxPlusAuthBusy('btn_vrcx_plus_vrchat_login', false, 'Logging in...', 'Login');
    }
}

async function verifyVrcxPlusVrchat2fa() {
    const code = document.getElementById('vrcx_plus_vrchat_2fa_code')?.value?.trim() || '';
    const method = document.getElementById('vrcx_plus_vrchat_2fa_method')?.value || 'totp';
    if (!code) {
        setVrcxPlusAuthText('Enter 2FA code.', true);
        return;
    }
    try {
        setVrcxPlusAuthBusy('btn_vrcx_plus_vrchat_2fa', true, 'Verifying...', 'Verify 2FA');
        setVrcxPlusAuthText('Verifying 2FA code...', false);
        await vrcxPlusPost('/vrcx-plus/vrchat/2fa', { code, method });
        document.getElementById('vrcx_plus_vrchat_2fa_code').value = '';
        setVrcxPlusAuthText('2FA verified. Logged in.', false);
        await refreshVrcxPlusState();
    } catch (e) {
        setVrcxPlusAuthText(`2FA verify failed: ${e.message}`, true);
    } finally {
        setVrcxPlusAuthBusy('btn_vrcx_plus_vrchat_2fa', false, 'Verifying...', 'Verify 2FA');
    }
}

async function logoutVrcxPlusVrchat() {
    try {
        await vrcxPlusPost('/vrcx-plus/vrchat/logout', {});
        setVrcxPlusAuthText('Logged out.', false);
        await refreshVrcxPlusState();
    } catch (e) {
        setVrcxPlusAuthText(`Logout failed: ${e.message}`, true);
    }
}

async function requestVrcxPlusVrchatEmailOtp() {
    try {
        setVrcxPlusAuthBusy('btn_vrcx_plus_vrchat_email_otp', true, 'Sending...', 'Send Email Code');
        setVrcxPlusAuthText('Requesting email verification code...', false);
        await vrcxPlusPost('/vrcx-plus/vrchat/email-otp', {});
        setVrcxPlusAuthText('Email OTP requested. Check your email.', false);
    } catch (e) {
        setVrcxPlusAuthText(`Email OTP request failed: ${e.message}`, true);
    } finally {
        setVrcxPlusAuthBusy('btn_vrcx_plus_vrchat_email_otp', false, 'Sending...', 'Send Email Code');
    }
}

function pickAvatarField(avatar, keys) {
    if (!avatar || typeof avatar !== 'object') return '';
    for (const key of keys) {
        const value = avatar[key];
        if (value === null || value === undefined) continue;
        const text = String(value).trim();
        if (text) return text;
    }
    return '';
}

function pushAvatarPlatformTokens(tokens, value) {
    if (value === null || value === undefined) return;
    if (typeof value === 'boolean') return;
    if (Array.isArray(value)) {
        value.forEach((entry) => pushAvatarPlatformTokens(tokens, entry));
        return;
    }
    if (typeof value === 'object') {
        Object.entries(value).forEach(([key, nested]) => {
            if (typeof nested === 'boolean') {
                if (nested) tokens.push(String(key || ''));
                return;
            }
            if (typeof nested === 'number') {
                if (nested) tokens.push(String(key || ''));
                return;
            }
            pushAvatarPlatformTokens(tokens, nested);
        });
        return;
    }
    const text = String(value || '').trim();
    if (!text || text.includes('://')) return;
    text
        .replace(/\|/g, ',')
        .replace(/;/g, ',')
        .replace(/\//g, ',')
        .split(',')
        .forEach((part) => {
            const cleaned = String(part || '').trim();
            if (cleaned) tokens.push(cleaned);
        });
}

function detectAvatarPlatforms(avatar) {
    if (!avatar || typeof avatar !== 'object') return [];
    const tokens = [];
    [
        'platform',
        'platforms',
        'platform_text',
        'platformsText',
        'supportedPlatforms',
        'supported_platforms',
        'releasePlatforms',
        'release_platforms',
        'targetPlatform',
        'targetPlatforms',
        'target_platforms',
        'compatibility',
        'devices',
        'deviceSupport',
        'tags',
        'labels'
    ].forEach((key) => pushAvatarPlatformTokens(tokens, avatar[key]));
    pushAvatarPlatformTokens(tokens, avatar.unityPackages);
    pushAvatarPlatformTokens(tokens, avatar.unity_packages);

    let pc = false;
    let quest = false;
    let phone = false;

    tokens.forEach((token) => {
        const compact = String(token || '')
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]/g, '');
        if (!compact) return;

        if (
            [
                'pc',
                'windows',
                'win',
                'desktop',
                'standalone',
                'standalonewindows',
                'windowsstandalone',
                'desktopvr',
                'steamvr'
            ].includes(compact) ||
            compact.startsWith('standalonewindows') ||
            compact.startsWith('windows')
        ) {
            pc = true;
        }

        if (
            ['quest', 'android', 'androidquest', 'questandroid', 'standaloneandroid', 'androidvr'].includes(compact) ||
            compact.includes('quest') ||
            compact.startsWith('androidquest')
        ) {
            quest = true;
        }

        if (
            ['phone', 'mobile', 'ios', 'iphone', 'ipad', 'androidmobile', 'mobileandroid', 'androidphone'].includes(compact) ||
            compact.includes('phone') ||
            compact.includes('mobile') ||
            compact.startsWith('ios')
        ) {
            phone = true;
        }
    });

    const platforms = [];
    if (pc) platforms.push('PC');
    if (quest) platforms.push('Quest');
    if (phone) platforms.push('Phone');
    return platforms;
}

function normalizeAvatarResult(avatar) {
    const avatarId = pickAvatarField(avatar, ['id', 'avatarId', 'avatar_id', 'assetId']);
    const avatarName = pickAvatarField(avatar, ['name', 'avatarName', 'avatar_name', 'displayName', 'title']);
    const author = pickAvatarField(avatar, ['authorName', 'author', 'author_name', 'creatorName', 'creator', 'uploaderName']);
    const status = pickAvatarField(avatar, ['releaseStatus', 'release_status', 'status', 'visibility']);
    const provider = pickAvatarField(avatar, ['provider', 'provider_name', 'source']);
    const platforms = detectAvatarPlatforms(avatar);
    const image = pickAvatarField(avatar, [
        'thumbnailImageUrl',
        'thumbnail',
        'thumbnail_url',
        'previewImageUrl',
        'imageUrl',
        'image',
        'icon'
    ]);
    const description = pickAvatarField(avatar, ['description', 'desc', 'bio', 'summary']);
    return {
        avatarId,
        avatarName: avatarName || (avatarId ? `Avatar ${avatarId}` : 'Unnamed Avatar'),
        author,
        status: status || '-',
        provider,
        platforms,
        platformsText: platforms.length ? platforms.join(', ') : 'Unknown',
        image,
        description
    };
}

async function searchVrcxPlusVrchatAvatars() {
    const query = document.getElementById('vrcx_plus_vrchat_avatar_query')?.value?.trim() || '';
    const n = parseInt(document.getElementById('vrcx_plus_vrchat_avatar_n')?.value || '40', 10);
    const useProvider = !!document.getElementById('vrcx_plus_provider_enabled')?.checked;
    const providerUrls = getVrcxPlusProviderUrlsInput();
    const wrap = document.getElementById('vrcx_plus_vrchat_avatar_results');
    if (!wrap) return;
    if (query.length < 2) {
        alert('Enter at least 2 characters.');
        return;
    }
    if (useProvider && !providerUrls.length) {
        alert('Add at least one avatar provider URL.');
        return;
    }
    if (!useProvider && !ensureVrcxPlusVrchatReady('avatar search')) {
        return;
    }
    try {
        setVrcxPlusStatus(useProvider ? 'Searching avatar providers...' : 'Searching VRChat avatars...');
        const payload = await vrcxPlusPost('/vrcx-plus/vrchat/avatar-search', {
            query,
            n,
            offset: 0,
            source: useProvider ? 'provider' : 'vrchat',
            urls: providerUrls,
            provider_url: providerUrls[0] || ''
        });
        const results = payload.results || [];
        if (!results.length) {
            wrap.textContent = 'No avatars found.';
            setVrcxPlusStatus('Ready', true);
            return;
        }
        wrap.innerHTML = results
            .slice(0, 100)
            .map((avatar) => {
                const normalized = normalizeAvatarResult(avatar);
                const avatarId = normalized.avatarId;
                const avatarName = normalized.avatarName;
                const author = normalized.author;
                const status = normalized.status;
                const provider = normalized.provider;
                const platformsText = normalized.platformsText;
                const image = normalized.image;
                const description = normalized.description;
                const meta = [author, status, provider].filter((value) => String(value || '').trim()).join(' | ');
                return `
                    <div class="vrcx-plus-item">
                        <span class="vrcx-plus-item-main">
                            ${
                                image
                                    ? `<a href="${escapeHtml(image)}" target="_blank" rel="noopener noreferrer" class="vrcx-plus-avatar-media">
                                        <img src="${escapeHtml(image)}" alt="${escapeHtml(avatarName)}" loading="lazy" />
                                    </a>`
                                    : '<span class="vrcx-plus-avatar-media vrcx-plus-avatar-placeholder">No image</span>'
                            }
                            <span>
                                <strong>${escapeHtml(avatarName)}</strong>
                                <br><small>${escapeHtml(meta || '-')}</small>
                                <br><small>Platforms: ${escapeHtml(platformsText)}</small>
                                <br><small>${escapeHtml(description)}</small>
                            </span>
                        </span>
                        <span class="vrcx-plus-actions">
                            ${avatarId ? `<button type="button" class="btn-off" onclick="wearVrchatAvatar('${escapeJs(avatarId)}')">Wear</button>` : ''}
                            <button type="button" class="btn-on" onclick="importVrcxPlusAvatar('${escapeJs(avatarId)}','${escapeJs(avatarName)}','${escapeJs(author)}','${escapeJs(status)}','${escapeJs(description)}')">Add</button>
                        </span>
                    </div>
                `;
            })
            .join('');
        if (useProvider) {
            const providerCount = Array.isArray(payload.providers) ? payload.providers.length : providerUrls.length;
            const failedCount = Array.isArray(payload.errors) ? payload.errors.length : 0;
            const failureText = failedCount ? `, ${failedCount} failed` : '';
            setVrcxPlusStatus(`Ready (${providerCount} providers${failureText})`, true);
            return;
        }
        setVrcxPlusStatus('Ready', true);
    } catch (e) {
        wrap.textContent = `Avatar search failed: ${e.message}`;
        if (isVrcxPlusAuthErrorMessage(e.message)) {
            await refreshVrcxPlusState();
            showVrcxPlusSubtab('vrchat');
        }
        setVrcxPlusStatus('Error');
    }
}

async function saveVrcxPlusProvider() {
    const enabled = !!document.getElementById('vrcx_plus_provider_enabled')?.checked;
    const urls = getVrcxPlusProviderUrlsInput();
    const url = urls[0] || '';
    if (enabled && !urls.length) {
        alert('Add at least one provider URL before enabling provider search.');
        return;
    }
    try {
        await vrcxPlusPost('/vrcx-plus/vrchat/provider', { enabled, url, urls });
        await refreshVrcxPlusState();
    } catch (e) {
        alert(`Failed to save provider: ${e.message}`);
    }
}

async function saveVrcxPlusAutoSnapshot() {
    const enabled = !!document.getElementById('vrcx_plus_auto_snapshot_enabled')?.checked;
    const minutes = parseInt(document.getElementById('vrcx_plus_auto_snapshot_minutes')?.value || '10', 10);
    const includeOffline = !!document.getElementById('vrcx_plus_auto_snapshot_include_offline')?.checked;
    try {
        await vrcxPlusPost('/vrcx-plus/vrchat/auto-snapshot', {
            enabled,
            minutes,
            include_offline: includeOffline
        });
        await refreshVrcxPlusState();
    } catch (e) {
        alert(`Failed to save auto snapshot: ${e.message}`);
    }
}

function scheduleVrcxPlusHistoryRefresh() {
    if (vrcxPlusAvatarHistoryRefreshTimer) {
        clearTimeout(vrcxPlusAvatarHistoryRefreshTimer);
        vrcxPlusAvatarHistoryRefreshTimer = null;
    }
    vrcxPlusAvatarHistoryRefreshTimer = setTimeout(async () => {
        try {
            vrcxPlusHistorySelectedUserId = '';
            await refreshVrcxPlusHistoryUsers();
            await refreshVrcxPlusAvatarHistory();
        } catch (e) {
            console.error('VRCX+ history refresh error:', e);
        }
    }, 220);
}

function scheduleVrcxPlusAvatarHistoryRefresh() {
    if (vrcxPlusAvatarHistoryRefreshTimer) {
        clearTimeout(vrcxPlusAvatarHistoryRefreshTimer);
        vrcxPlusAvatarHistoryRefreshTimer = null;
    }
    vrcxPlusAvatarHistoryRefreshTimer = setTimeout(() => {
        refreshVrcxPlusAvatarHistory();
    }, 220);
}

async function refreshVrcxPlusHistoryUsers() {
    const wrap = document.getElementById('vrcx_plus_history_users');
    if (!wrap) return;
    const query = document.getElementById('vrcx_plus_history_user_filter')?.value?.trim() || '';
    const recent = document.getElementById('vrcx_plus_history_recent_filter')?.value || 'all';
    try {
        const params = new URLSearchParams();
        if (query) params.set('q', query);
        if (recent && recent !== 'all') params.set('recent', recent);
        const response = await fetch(`/vrcx-plus/friend-history/users${params.toString() ? `?${params.toString()}` : ''}`);
        const payload = await response.json();
        const users = payload?.users || [];
        if (!users.length) {
            wrap.textContent = 'No users yet.';
            const entries = document.getElementById('vrcx_plus_history_entries');
            if (entries) entries.textContent = 'Select a user to view history.';
            await refreshVrcxPlusAvatarHistory();
            return;
        }
        wrap.innerHTML = users
            .slice(0, 100)
            .map((user) => {
                const active = user.id === vrcxPlusHistorySelectedUserId;
                return `<div class="vrcx-plus-item"><span><strong>${escapeHtml(user.displayName || user.id)}</strong><br><small>Snapshots: ${user.snapshots || 0} | Last seen: ${escapeHtml(user.last_seen || '-')}</small></span><span class="vrcx-plus-actions"><button type="button" class="${active ? 'btn-on' : 'btn-off'}" onclick="loadVrcxPlusFriendHistory('${escapeJs(user.id)}')">Open</button></span></div>`;
            })
            .join('');
        if (!vrcxPlusHistorySelectedUserId && users[0]?.id) {
            await loadVrcxPlusFriendHistory(users[0].id, false);
        } else if (vrcxPlusHistorySelectedUserId) {
            await loadVrcxPlusFriendHistory(vrcxPlusHistorySelectedUserId, false);
        }
        await refreshVrcxPlusAvatarHistory();
    } catch (e) {
        wrap.textContent = `Failed to load users: ${e.message}`;
    }
}

async function loadVrcxPlusFriendHistory(userId, refreshUsers = true) {
    const entries = document.getElementById('vrcx_plus_history_entries');
    if (!entries || !userId) return;
    vrcxPlusHistorySelectedUserId = userId;
    if (refreshUsers) {
        await refreshVrcxPlusHistoryUsers();
    }
    try {
        const payload = await vrcxPlusPost('/vrcx-plus/friend-history', { user_id: userId });
        const history = payload.history || [];
        if (!history.length) {
            entries.textContent = 'No history for this user.';
            return;
        }
        entries.innerHTML = history
            .slice(0, 120)
            .map((row) => {
                const avatarId = row.currentAvatarId || '';
                const avatarName = row.currentAvatarName || '';
                const wearBtn = avatarId
                    ? `<button type="button" class="btn-off" onclick="wearVrchatAvatar('${escapeJs(avatarId)}')">Wear</button>`
                    : '';
                const avatarSummary = avatarId
                    ? `${avatarName ? `${escapeHtml(avatarName)} ` : ''}(${escapeHtml(avatarId)})`
                    : 'Unknown';
                return `<div class="vrcx-plus-item"><span><strong>${escapeHtml(row.displayName || userId)}</strong><br><small>${escapeHtml(row.created_at || '')} | ${escapeHtml(row.status || '-')} | ${escapeHtml(row.location || '-')}</small><br><small>Avatar: ${avatarSummary}</small></span><span class="vrcx-plus-actions">${wearBtn}</span></div>`;
            })
            .join('');
        await refreshVrcxPlusAvatarHistory();
    } catch (e) {
        entries.textContent = `Failed to load history: ${e.message}`;
    }
}

async function refreshVrcxPlusAvatarHistory() {
    const wrap = document.getElementById('vrcx_plus_avatar_history');
    if (!wrap) return;
    try {
        const query = document.getElementById('vrcx_plus_avatar_history_query')?.value?.trim() || '';
        const recent = document.getElementById('vrcx_plus_avatar_history_recent')?.value || 'all';
        const selectedOnly = !!document.getElementById('vrcx_plus_avatar_history_selected_only')?.checked;
        const params = new URLSearchParams();
        if (query) params.set('q', query);
        if (recent && recent !== 'all') params.set('recent', recent);
        if (selectedOnly && vrcxPlusHistorySelectedUserId) params.set('user_id', vrcxPlusHistorySelectedUserId);
        const response = await fetch(`/vrcx-plus/avatar-history${params.toString() ? `?${params.toString()}` : ''}`);
        const payload = await response.json();
        const avatars = payload?.avatars || [];
        if (!avatars.length) {
            wrap.textContent = 'No captured avatars yet.';
            return;
        }
        wrap.innerHTML = avatars
            .slice(0, 250)
            .map((row) => {
                const avatarId = row.avatar_id || '';
                const avatarName = row.name || 'Unknown Avatar';
                const userNames = row.user_names || '';
                const thumb = row.thumbnail_image_url || row.image_url || '';
                const seenCount = Number.isFinite(Number(row.seen_count)) ? Number(row.seen_count) : 0;
                const wearBtn = avatarId
                    ? `<button type="button" class="btn-on" onclick="wearVrchatAvatar('${escapeJs(avatarId)}')">Wear</button>`
                    : '';
                return `
                    <div class="vrcx-plus-item">
                        <span class="vrcx-plus-item-main">
                            ${
                                thumb
                                    ? `<a href="${escapeHtml(thumb)}" target="_blank" rel="noopener noreferrer" class="vrcx-plus-avatar-media">
                                        <img src="${escapeHtml(thumb)}" alt="${escapeHtml(avatarName)}" loading="lazy" />
                                    </a>`
                                    : '<span class="vrcx-plus-avatar-media vrcx-plus-avatar-placeholder">No image</span>'
                            }
                            <span>
                                <strong>${escapeHtml(avatarName)}</strong>
                                <br><small>${escapeHtml(avatarId)}</small>
                                <br><small>Seen: ${seenCount} | Last: ${escapeHtml(row.last_seen || '-')}</small>
                                <br><small>Users: ${escapeHtml(userNames || '-')}</small>
                            </span>
                        </span>
                        <span class="vrcx-plus-actions">${wearBtn}</span>
                    </div>
                `;
            })
            .join('');
    } catch (e) {
        wrap.textContent = `Failed to load captured avatars: ${e.message}`;
    }
}

async function importVrcxPlusAvatar(id, name, author, status, description) {
    try {
        await vrcxPlusPost('/vrcx-plus/item', {
            type: 'avatar',
            name: name || id || 'Avatar',
            author: author || '',
            status: (status || 'public').toLowerCase() === 'private' ? 'private' : 'public',
            description: description || '',
            external_id: id || ''
        });
        await refreshVrcxPlusState();
    } catch (e) {
        alert(`Failed to add avatar: ${e.message}`);
    }
}

async function wearVrchatAvatar(avatarId) {
    if (!avatarId) {
        alert('No avatar id available.');
        return;
    }
    if (!ensureVrcxPlusVrchatReady('switching avatars')) {
        return;
    }
    try {
        setVrcxPlusStatus('Switching avatar...');
        await vrcxPlusPost('/vrcx-plus/vrchat/avatar-select', { avatar_id: avatarId });
        setVrcxPlusStatus('Avatar switched', true);
    } catch (e) {
        if (isVrcxPlusAuthErrorMessage(e.message)) {
            await refreshVrcxPlusState();
            showVrcxPlusSubtab('vrchat');
        }
        alert(`Failed to switch avatar: ${e.message}`);
        setVrcxPlusStatus('Error');
    }
}

async function captureVrcxPlusFriendSnapshot() {
    if (!ensureVrcxPlusVrchatReady('capturing friend snapshots')) {
        return;
    }
    try {
        const includeOffline = !!document.getElementById('vrcx_plus_vrchat_include_offline')?.checked;
        setVrcxPlusStatus('Capturing friend snapshot...');
        await vrcxPlusPost('/vrcx-plus/vrchat/friends-snapshot', {
            include_offline: includeOffline,
            max_results: 120
        });
        await refreshVrcxPlusState();
    } catch (e) {
        if (isVrcxPlusAuthErrorMessage(e.message)) {
            await refreshVrcxPlusState();
            showVrcxPlusSubtab('vrchat');
        }
        alert(`Failed to capture snapshot: ${e.message}`);
        setVrcxPlusStatus('Error');
    }
}

function resetVrcxPlusFilters() {
    const setValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.value = value;
    };
    setValue('vrcx_plus_query', '');
    setValue('vrcx_plus_type', 'all');
    setValue('vrcx_plus_status', 'all');
    setValue('vrcx_plus_sort', 'updated');
    setValue('vrcx_plus_author', '');
    const favOnly = document.getElementById('vrcx_plus_favorites_only');
    if (favOnly) favOnly.checked = false;
    runVrcxPlusSearch();
}

function escapeHtml(value) {
    return String(value || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function escapeJs(value) {
    return String(value || '')
        .replaceAll('\\', '\\\\')
        .replaceAll("'", "\\'");
}

function setupButtons() {
    document.getElementById('btn_chatbox')?.addEventListener('click', toggleChatbox);
    document.getElementById('btn_time')?.addEventListener('click', toggleTime);
    document.getElementById('btn_custom')?.addEventListener('click', toggleCustom);
    document.getElementById('btn_music')?.addEventListener('click', toggleMusic);
    document.getElementById('btn_window')?.addEventListener('click', toggleWindow);
    document.getElementById('btn_heartrate')?.addEventListener('click', toggleHeartRate);
    document.getElementById('btn_weather')?.addEventListener('click', toggleWeather);
    document.getElementById('btn_slim_chatbox')?.addEventListener('click', toggleSlimChatbox);
    document.getElementById('btn_system_stats')?.addEventListener('click', toggleSystemStats);
    document.getElementById('btn_afk')?.addEventListener('click', toggleAfk);
    document.getElementById('btn_music_progress')?.addEventListener('click', toggleMusicProgress);
}

function setupStreamerMode() {
    const streamerModeEnabled = document.getElementById('toggle_streamer_btn')?.textContent.includes('ON');
    
    if (streamerModeEnabled) {
        const sensitiveFields = [
            document.querySelector('input[name="quest_ip"]'),
            document.querySelector('input[name="spotify_client_id"]'),
            document.querySelector('input[name="spotify_client_secret"]')
        ];
        
        sensitiveFields.forEach(field => {
            if (field && field.value && !field.value.includes('***')) {
                field.type = 'password';
                
                const container = field.parentElement;
                let revealBtn = container.querySelector('.reveal-btn');
                
                if (!revealBtn) {
                    revealBtn = document.createElement('button');
                    revealBtn.type = 'button';
                    revealBtn.className = 'reveal-btn btn-on';
                    revealBtn.textContent = '👁';
                    revealBtn.style.marginLeft = '8px';
                    revealBtn.style.padding = '4px 12px';
                    
                    let isRevealed = false;
                    revealBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        isRevealed = !isRevealed;
                        field.type = isRevealed ? 'text' : 'password';
                        revealBtn.textContent = isRevealed ? '👁‍🗨' : '👁';
                    });
                    
                    field.after(revealBtn);
                }
            }
        });
    }
}

function setupAdvanced() {
    document.getElementById('random_order_btn').addEventListener('click', async (e) => {
        await fetch('/toggle_random_order', { method: 'POST' });
        await updateAdvancedButtons();
        updateMessageWeightsVisibility();
    });
    
    document.getElementById('show_module_icons_btn').addEventListener('click', async (e) => {
        await fetch('/toggle_module_icons', { method: 'POST' });
        await updateAdvancedButtons();
    });
    
    document.getElementById('toggle_theme_btn').addEventListener('click', async () => {
        const response = await fetch('/toggle_theme', { method: 'POST' });
        const data = await response.json();
        document.body.className = data.theme === 'light' ? 'light' : '';
        updateDisplayOptionButtons();
    });
    
    document.getElementById('toggle_streamer_btn').addEventListener('click', async () => {
        await fetch('/toggle_streamer_mode', { method: 'POST' });
        updateDisplayOptionButtons();
        location.reload();
    });
    
    document.getElementById('toggle_compact_btn').addEventListener('click', async () => {
        await fetch('/toggle_compact_mode', { method: 'POST' });
        updateDisplayOptionButtons();
        location.reload();
    });
    
    document.getElementById('download_settings_btn').addEventListener('click', async (e) => {
        e.preventDefault();
        const btn = e.target;
        const originalText = btn.textContent;
        
        try {
            btn.textContent = 'Downloading...';
            btn.disabled = true;
            
            // Check if running in PyWebview (has pywebview API)
            if (window.pywebview) {
                const result = await window.pywebview.api.download_settings();
                if (result.success) {
                    btn.textContent = '✓ Saved to Downloads!';
                    console.log('File saved to:', result.path);
                } else {
                    throw new Error(result.error);
                }
            } else {
                // Browser fallback
                const response = await fetch('/download_settings');
                if (!response.ok) throw new Error('Download failed');
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `vrchat_chatbox_backup_${new Date().toISOString().slice(0,10).replace(/-/g, '')}.json`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);
                btn.textContent = '✓ Downloaded!';
            }
            
            setTimeout(() => {
                btn.textContent = originalText;
                btn.disabled = false;
            }, 2000);
        } catch (error) {
            btn.textContent = '✗ Failed';
            setTimeout(() => {
                btn.textContent = originalText;
                btn.disabled = false;
            }, 2000);
            console.error('Download error:', error);
        }
    });
    
    document.getElementById('upload_settings_btn').addEventListener('click', (e) => {
        e.preventDefault();
        console.log('Upload settings clicked!');
        document.getElementById('upload_settings_file').click();
    });
    
    document.getElementById('upload_settings_file').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        try {
            const text = await file.text();
            const settings = JSON.parse(text);
            
            const response = await fetch('/upload_settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            
            if (response.ok) {
                alert('Settings uploaded successfully!');
                await updateStatus();
            } else {
                alert('Failed to upload settings. Please check the file format.');
            }
        } catch (error) {
            alert('Invalid settings file. Please upload a valid JSON file.');
        }
        
        e.target.value = '';
    });
    
    document.getElementById('download_log_btn').addEventListener('click', async (e) => {
        e.preventDefault();
        const btn = e.target;
        const originalText = btn.textContent;
        
        try {
            btn.textContent = 'Downloading...';
            btn.disabled = true;
            
            // Check if running in PyWebview (has pywebview API)
            if (window.pywebview) {
                const result = await window.pywebview.api.download_log();
                if (result.success) {
                    btn.textContent = '✓ Saved to Downloads!';
                    console.log('File saved to:', result.path);
                } else {
                    if (result.error === 'No error log found') {
                        throw new Error('No error log found');
                    }
                    throw new Error(result.error);
                }
            } else {
                // Browser fallback
                const response = await fetch('/download_log');
                if (!response.ok) {
                    if (response.status === 404) {
                        throw new Error('No error log found');
                    }
                    throw new Error('Download failed');
                }
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `vrchat_errors_${new Date().toISOString().slice(0,10).replace(/-/g, '')}.log`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);
                btn.textContent = '✓ Downloaded!';
            }
            
            setTimeout(() => {
                btn.textContent = originalText;
                btn.disabled = false;
            }, 2000);
        } catch (error) {
            btn.textContent = error.message === 'No error log found' ? '✗ No Log Found' : '✗ Failed';
            setTimeout(() => {
                btn.textContent = originalText;
                btn.disabled = false;
            }, 2000);
            console.error('Download error:', error);
        }
    });
    
    document.getElementById('reset_defaults_btn').addEventListener('click', async () => {
        if (confirm('Reset all settings to defaults? This cannot be undone.')) {
            await fetch('/reset_settings', { method: 'POST' });
            location.reload();
        }
    });
    
    document.getElementById('add_message_btn').addEventListener('click', async () => {
        const newText = prompt('Enter new message:');
        if (newText && newText.trim()) {
            await fetch('/add_custom_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: newText.trim() })
            });
            loadCustomMessages();
            loadPerMessageTimings();
            loadMessageWeights();
        }
    });
    
    const windowTrackingBtn = document.getElementById('toggle_window_tracking_btn');
    if (windowTrackingBtn) {
        windowTrackingBtn.addEventListener('click', async () => {
            const response = await fetch('/toggle_window_tracking', { method: 'POST' });
            const data = await response.json();
            windowTrackingBtn.className = data.window_tracking_enabled ? 'btn-on' : 'btn-off';
            windowTrackingBtn.textContent = `Window Tracking: ${data.window_tracking_enabled ? 'ON' : 'OFF'}`;
        });
    }
    
    const windowTrackingMode = document.getElementById('window_tracking_mode');
    if (windowTrackingMode) {
        windowTrackingMode.addEventListener('change', async (e) => {
            const mode = e.target.value;
            await fetch('/save_window_tracking_mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode })
            });
        });
    }
    
    document.getElementById('save_emojis_btn').addEventListener('click', async () => {
        const timeEmoji = document.getElementById('time_emoji').value;
        const songEmoji = document.getElementById('song_emoji').value;
        const windowEmoji = document.getElementById('window_emoji').value;
        const heartrateEmoji = document.getElementById('heartrate_emoji').value;
        
        await fetch('/save_emoji_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                time_emoji: timeEmoji,
                song_emoji: songEmoji,
                window_emoji: windowEmoji,
                heartrate_emoji: heartrateEmoji
            })
        });
        alert('Emojis saved successfully!');
    });
    
    document.getElementById('save_premium_styling_btn').addEventListener('click', async () => {
        const customBackground = document.getElementById('custom_background').value;
        const customButtonColor = document.getElementById('custom_button_color').value;
        
        const response = await fetch('/save_premium_styling', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                custom_background: customBackground,
                custom_button_color: customButtonColor
            })
        });
        
        if (response.ok) {
            applyPremiumStyling(customBackground, customButtonColor);
            alert('Customization saved successfully!');
        } else {
            alert('Failed to save customization.');
        }
    });
    
    document.getElementById('toggle_heart_rate_enabled_btn')?.addEventListener('click', async () => {
        const response = await fetch('/toggle_heart_rate_enabled', { method: 'POST' });
        const data = await response.json();
        const btn = document.getElementById('toggle_heart_rate_enabled_btn');
        btn.className = data.heart_rate_enabled ? 'btn-on' : 'btn-off';
        btn.textContent = `Heart Rate Tracking: ${data.heart_rate_enabled ? 'ON' : 'OFF'}`;
    });
    
    document.getElementById('heart_rate_source')?.addEventListener('change', (e) => {
        const source = e.target.value;
        document.getElementById('pulsoid_settings').style.display = source === 'pulsoid' ? 'block' : 'none';
        document.getElementById('hyperate_settings').style.display = source === 'hyperate' ? 'block' : 'none';
        document.getElementById('custom_api_settings').style.display = source === 'custom' ? 'block' : 'none';
    });
    
    document.getElementById('save_heart_rate_settings_btn')?.addEventListener('click', async () => {
        const source = document.getElementById('heart_rate_source').value;
        const pulsoidToken = document.getElementById('heart_rate_pulsoid_token').value;
        const hyperateId = document.getElementById('heart_rate_hyperate_id').value;
        const customApi = document.getElementById('heart_rate_custom_api').value;
        const updateInterval = document.getElementById('heart_rate_update_interval').value;
        const hrShowTrend = document.getElementById('hr_show_trend')?.checked ?? true;
        const hrShowStats = document.getElementById('hr_show_stats')?.checked ?? false;
        
        await fetch('/save_heart_rate_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                source,
                pulsoid_token: pulsoidToken,
                hyperate_id: hyperateId,
                custom_api: customApi,
                update_interval: updateInterval,
                hr_show_trend: hrShowTrend,
                hr_show_stats: hrShowStats
            })
        });
        alert('Heart rate settings saved successfully!');
    });
    
    document.getElementById('generate_ai_btn')?.addEventListener('click', async () => {
        const mood = document.getElementById('ai_mood').value;
        const theme = document.getElementById('ai_theme').value;
        
        try {
            const response = await fetch('/generate_ai_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mood, theme, max_length: 30 })
            });
            
            const data = await response.json();
            
            if (data.ok && data.message) {
                document.getElementById('ai_message_text').textContent = data.message;
                document.getElementById('ai_result').style.display = 'block';
                document.getElementById('ai_result').dataset.message = data.message;
            } else {
                alert(data.error || 'Failed to generate message. Make sure OPENAI_API_KEY is set.');
            }
        } catch (error) {
            alert('Error: ' + error.message);
        }
    });
    
    document.getElementById('add_ai_message_btn')?.addEventListener('click', async () => {
        const message = document.getElementById('ai_result').dataset.message;
        if (message) {
            await fetch('/add_custom_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: message })
            });
            loadCustomMessages();
            document.getElementById('ai_result').style.display = 'none';
            alert('Message added to custom messages!');
        }
    });
    
    document.getElementById('check_updates_btn')?.addEventListener('click', async () => {
        try {
            const response = await fetch('/update_info');
            const data = await response.json();
            
            document.getElementById('current_version').textContent = data.current_version;
            
            if (data.update_info && data.update_info.update_available) {
                const info = data.update_info;
                document.getElementById('latest_version').textContent = info.latest_version;
                document.getElementById('release_name').textContent = info.release_name;
                document.getElementById('release_notes').textContent = info.release_notes.substring(0, 200) + '...';
                document.getElementById('release_link').href = info.release_url;
                document.getElementById('update_info').style.display = 'block';
                document.getElementById('no_update_info').style.display = 'none';
            } else {
                document.getElementById('update_info').style.display = 'none';
                document.getElementById('no_update_info').style.display = 'block';
            }
        } catch (error) {
            alert('Error checking for updates: ' + error.message);
        }
    });
    
    loadProfiles();
    
    document.getElementById('save_profile_btn')?.addEventListener('click', async () => {
        const name = prompt('Enter profile name:');
        if (name && name.trim()) {
            try {
                const response = await fetch('/save_profile', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name.trim() })
                });
                const data = await response.json();
                if (data.ok) {
                    alert(data.message || 'Profile saved!');
                    loadProfiles();
                } else {
                    alert(data.error || 'Failed to save profile');
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
    });
    
    document.getElementById('load_profile_btn')?.addEventListener('click', async () => {
        const select = document.getElementById('profile_select');
        const name = select.value;
        if (name) {
            try {
                const response = await fetch('/load_profile', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name })
                });
                const data = await response.json();
                if (data.ok) {
                    alert('Profile loaded! Reloading page...');
                    location.reload();
                } else {
                    alert(data.error || 'Failed to load profile');
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        } else {
            alert('Please select a profile first');
        }
    });
    
    document.getElementById('delete_profile_btn')?.addEventListener('click', async () => {
        const select = document.getElementById('profile_select');
        const name = select.value;
        if (name) {
            if (confirm(`Delete profile "${name}"?`)) {
                try {
                    const response = await fetch('/delete_profile', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name })
                    });
                    const data = await response.json();
                    if (data.ok) {
                        alert('Profile deleted!');
                        loadProfiles();
                    } else {
                        alert(data.error || 'Failed to delete profile');
                    }
                } catch (error) {
                    alert('Error: ' + error.message);
                }
            }
        } else {
            alert('Please select a profile first');
        }
    });
    
    document.getElementById('text_effect_select')?.addEventListener('change', async (e) => {
        const effect = e.target.value;
        try {
            await fetch('/set_text_effect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ effect })
            });
        } catch (error) {
            console.error('Error setting text effect:', error);
        }
    });
    
    document.getElementById('chatbox_frame_select')?.addEventListener('change', async (e) => {
        const frame = e.target.value;
        try {
            const response = await fetch('/set_chatbox_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frame })
            });
            const data = await response.json();
            if (data.preview) {
                document.getElementById('frame_preview_box').textContent = data.preview;
            }
        } catch (error) {
            console.error('Error setting chatbox frame:', error);
        }
    });
    
    loadCurrentFrame();
    
    document.getElementById('save_weather_btn')?.addEventListener('click', async () => {
        const location = document.getElementById('weather_location').value;
        const tempUnit = document.getElementById('weather_temp_unit').value;
        try {
            await fetch('/save_weather_settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ location, temp_unit: tempUnit })
            });
            alert('Weather settings saved!');
        } catch (error) {
            alert('Error: ' + error.message);
        }
    });
    
    const typedDurationSlider = document.getElementById('typed_message_duration');
    const typedDurationValue = document.getElementById('typed_duration_value');
    if (typedDurationSlider && typedDurationValue) {
        typedDurationSlider.addEventListener('input', () => {
            typedDurationValue.textContent = typedDurationSlider.value + 's';
        });
        
        typedDurationSlider.addEventListener('change', async () => {
            await saveTypingSettings();
        });
    }
    
    const typingIndicatorCheckbox = document.getElementById('typing_indicator_enabled');
    if (typingIndicatorCheckbox) {
        typingIndicatorCheckbox.addEventListener('change', async () => {
            await saveTypingSettings();
        });
    }
    
    const windowPrefixInput = document.getElementById('window_prefix');
    const windowPrefixPreview = document.getElementById('window_prefix_preview');
    if (windowPrefixInput && windowPrefixPreview) {
        windowPrefixInput.addEventListener('input', () => {
            const prefix = windowPrefixInput.value.trim();
            if (prefix) {
                windowPrefixPreview.textContent = prefix + ' VRChat';
            } else {
                windowPrefixPreview.textContent = 'VRChat';
            }
        });
    }
    
    const saveWindowSettingsBtn = document.getElementById('save_window_settings_btn');
    if (saveWindowSettingsBtn) {
        saveWindowSettingsBtn.addEventListener('click', async () => {
            await saveWindowSettings();
        });
    }
    
    const afkTimeoutSlider = document.getElementById('afk_timeout');
    const afkTimeoutValue = document.getElementById('afk_timeout_value');
    const afkMessageInput = document.getElementById('afk_message');
    const afkPreview = document.getElementById('afk_preview');
    
    function updateAfkPreview() {
        if (!afkPreview) return;
        const secs = parseInt(afkTimeoutSlider?.value || 300);
        const mins = Math.floor(secs / 60);
        const customMsg = afkMessageInput?.value?.trim() || '';
        const showDuration = document.getElementById('afk_show_duration')?.checked ?? true;
        
        if (showDuration) {
            const durationText = mins === 1 ? '1 minute' : mins + ' minutes';
            if (customMsg) {
                afkPreview.textContent = customMsg + ' for ' + durationText;
            } else {
                afkPreview.textContent = 'AFK for ' + durationText;
            }
        } else {
            afkPreview.textContent = customMsg || 'AFK';
        }
    }
    
    if (afkTimeoutSlider && afkTimeoutValue) {
        afkTimeoutSlider.addEventListener('input', () => {
            const secs = parseInt(afkTimeoutSlider.value);
            const mins = Math.floor(secs / 60);
            afkTimeoutValue.textContent = mins + ' min';
            updateAfkPreview();
        });
    }
    
    if (afkMessageInput) {
        afkMessageInput.addEventListener('input', updateAfkPreview);
    }
    
    const afkShowDurationCheckbox = document.getElementById('afk_show_duration');
    if (afkShowDurationCheckbox) {
        afkShowDurationCheckbox.addEventListener('change', updateAfkPreview);
    }
    
    updateAfkPreview();
    
    const saveAfkBtn = document.getElementById('save_afk_settings_btn');
    if (saveAfkBtn) {
        saveAfkBtn.addEventListener('click', async () => {
            await saveAfkSettings();
        });
    }
    
    const saveSystemStatsBtn = document.getElementById('save_system_stats_settings_btn');
    if (saveSystemStatsBtn) {
        saveSystemStatsBtn.addEventListener('click', async () => {
            await saveSystemStatsSettings();
        });
    }
    
    const resetHrStatsBtn = document.getElementById('reset_hr_stats_btn');
    if (resetHrStatsBtn) {
        resetHrStatsBtn.addEventListener('click', async () => {
            try {
                await fetch('/reset_hr_stats', { method: 'POST' });
                alert('Heart rate session stats reset!');
            } catch (e) {
                console.error('Failed to reset HR stats:', e);
            }
        });
    }
    
    const hrSimulatorBtn = document.getElementById('toggle_hr_simulator_btn');
    if (hrSimulatorBtn) {
        hrSimulatorBtn.addEventListener('click', async () => {
            try {
                const response = await fetch('/toggle_hr_simulator', { method: 'POST' });
                const data = await response.json();
                hrSimulatorBtn.className = data.enabled ? 'btn-on' : 'btn-off';
                hrSimulatorBtn.textContent = `HR Simulator: ${data.enabled ? 'ON' : 'OFF'}`;
                if (data.enabled) {
                    alert('Heart Rate Simulator enabled! Fake heart rate data will be generated for testing.');
                }
            } catch (e) {
                console.error('Failed to toggle HR simulator:', e);
            }
        });
    }
    
    updateDisplayOptionButtons();
    updateAdvancedButtons();
    updateMessageWeightsVisibility();
}

async function loadProfiles() {
    try {
        const response = await fetch('/profiles');
        const data = await response.json();
        const select = document.getElementById('profile_select');
        
        if (select) {
            select.innerHTML = '<option value="">-- Select a profile --</option>';
            data.profiles.forEach(profile => {
                const option = document.createElement('option');
                option.value = profile;
                option.textContent = profile;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading profiles:', error);
    }
}

async function loadCurrentFrame() {
    try {
        const response = await fetch('/get_frame_styles');
        const data = await response.json();
        const select = document.getElementById('chatbox_frame_select');
        const previewBox = document.getElementById('frame_preview_box');
        
        if (select && data.current) {
            select.value = data.current;
            
            if (data.current !== 'none' && previewBox) {
                const previewResponse = await fetch('/preview_frame', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ frame: data.current })
                });
                const previewData = await previewResponse.json();
                if (previewData.preview) {
                    previewBox.textContent = previewData.preview;
                }
            }
        }
    } catch (error) {
        console.error('Error loading current frame:', error);
    }
}

async function saveTypingSettings() {
    const durationSlider = document.getElementById('typed_message_duration');
    const indicatorCheckbox = document.getElementById('typing_indicator_enabled');
    
    const duration = durationSlider ? parseInt(durationSlider.value) : 5;
    const indicatorEnabled = indicatorCheckbox ? indicatorCheckbox.checked : true;
    
    try {
        await fetch('/save_typing_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                typed_message_duration: duration,
                typing_indicator_enabled: indicatorEnabled
            })
        });
    } catch (error) {
        console.error('Error saving typing settings:', error);
    }
}

async function saveWindowSettings() {
    const prefixInput = document.getElementById('window_prefix');
    
    try {
        await fetch('/save_window_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                window_prefix: prefixInput?.value ?? ''
            })
        });
        alert('Window settings saved!');
    } catch (error) {
        console.error('Error saving window settings:', error);
    }
}

async function saveAfkSettings() {
    const timeoutSlider = document.getElementById('afk_timeout');
    const messageInput = document.getElementById('afk_message');
    const showDurationCheckbox = document.getElementById('afk_show_duration');
    
    try {
        await fetch('/save_afk_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                afk_timeout: parseInt(timeoutSlider?.value || 300),
                afk_message: messageInput?.value || '',
                afk_show_duration: showDurationCheckbox?.checked ?? true
            })
        });
        alert('AFK settings saved!');
    } catch (error) {
        console.error('Error saving AFK settings:', error);
    }
}

async function saveSystemStatsSettings() {
    const showCpu = document.getElementById('show_cpu')?.checked ?? true;
    const showRam = document.getElementById('show_ram')?.checked ?? true;
    const showGpu = document.getElementById('show_gpu')?.checked ?? false;
    const showNetwork = document.getElementById('show_network')?.checked ?? false;
    
    try {
        await fetch('/save_system_stats_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                show_cpu: showCpu,
                show_ram: showRam,
                show_gpu: showGpu,
                show_network: showNetwork
            })
        });
        alert('System stats settings saved!');
    } catch (error) {
        console.error('Error saving system stats settings:', error);
    }
}

async function updateAdvancedButtons() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        
        const randomOrderBtn = document.getElementById('random_order_btn');
        const showIconsBtn = document.getElementById('show_module_icons_btn');
        
        if (randomOrderBtn) {
            randomOrderBtn.className = data.random_order ? 'btn-on' : 'btn-off';
            randomOrderBtn.textContent = `Random Order: ${data.random_order ? 'ON' : 'OFF'}`;
        }
        
        if (showIconsBtn) {
            showIconsBtn.className = data.show_module_icons ? 'btn-on' : 'btn-off';
            showIconsBtn.textContent = `Module Icons: ${data.show_module_icons ? 'ON' : 'OFF'}`;
        }
    } catch (error) {
        console.error('Error updating advanced buttons:', error);
    }
}

async function updateMessageWeightsVisibility() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        const weightsSection = document.getElementById('message_weights_section');
        
        if (weightsSection) {
            weightsSection.style.display = data.random_order ? 'block' : 'none';
        }
    } catch (error) {
        console.error('Error updating weights visibility:', error);
    }
}

function setupProgressStyle() {
    const select = document.getElementById('select_progress_style');
    select.addEventListener('change', async () => {
        try {
            await fetch('/set_progress_style', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ style: select.value })
            });
        } catch (error) {
            console.error('Error setting progress style:', error);
        }
    });
}

async function loadCustomMessages() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        customMessages = data.custom_texts || [];
        renderInlineMessages();
    } catch (error) {
        console.error('Error loading custom messages:', error);
    }
}

function renderInlineMessages() {
    const container = document.getElementById('inline_messages_container');
    if (!container) return;
    
    container.innerHTML = '';
    
    customMessages.forEach((msg, idx) => {
        const div = document.createElement('div');
        div.style.cssText = 'display:flex;gap:8px;margin-bottom:8px;align-items:center;';
        
        const num = document.createElement('span');
        num.textContent = `${idx + 1}.`;
        num.style.cssText = 'min-width:30px;color:#0af;font-weight:700;';
        
        const upBtn = document.createElement('button');
        upBtn.textContent = '▲';
        upBtn.className = 'btn-on';
        upBtn.style.cssText = 'padding:4px 10px;font-size:10px;';
        upBtn.disabled = idx === 0;
        if (idx === 0) upBtn.style.opacity = '0.3';
        upBtn.addEventListener('click', () => moveMessage(idx, 'up'));
        
        const downBtn = document.createElement('button');
        downBtn.textContent = '▼';
        downBtn.className = 'btn-on';
        downBtn.style.cssText = 'padding:4px 10px;font-size:10px;';
        downBtn.disabled = idx === customMessages.length - 1;
        if (idx === customMessages.length - 1) downBtn.style.opacity = '0.3';
        downBtn.addEventListener('click', () => moveMessage(idx, 'down'));
        
        const input = document.createElement('input');
        input.type = 'text';
        input.value = msg;
        input.style.cssText = 'flex:1;';
        input.addEventListener('blur', () => updateMessage(idx, input.value));
        
        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = '🗑';
        deleteBtn.className = 'btn-off';
        deleteBtn.style.cssText = 'padding:4px 8px;';
        deleteBtn.addEventListener('click', () => deleteMessage(idx));
        
        div.appendChild(num);
        div.appendChild(upBtn);
        div.appendChild(downBtn);
        div.appendChild(input);
        div.appendChild(deleteBtn);
        container.appendChild(div);
    });
}

async function updateMessage(index, text) {
    try {
        await fetch('/update_custom_inline', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index, text })
        });
    } catch (error) {
        console.error('Error updating message:', error);
    }
}

async function deleteMessage(index) {
    try {
        await fetch('/delete_custom_message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index })
        });
        loadCustomMessages();
        loadPerMessageTimings();
        loadMessageWeights();
    } catch (error) {
        console.error('Error deleting message:', error);
    }
}

async function moveMessage(index, direction) {
    try {
        await fetch('/move_custom_message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index, direction })
        });
        loadCustomMessages();
        loadPerMessageTimings();
        loadMessageWeights();
    } catch (error) {
        console.error('Error moving message:', error);
    }
}

async function loadPerMessageTimings() {
    const container = document.getElementById('per_message_timing_container');
    if (!container) return;
    
    try {
        const response = await fetch('/status');
        const data = await response.json();
        customMessages = data.custom_texts || [];
        const savedIntervals = data.per_message_intervals || {};
        
        container.innerHTML = '';
        
        customMessages.forEach((msg, idx) => {
            const div = document.createElement('div');
            div.style.cssText = 'display:flex;gap:8px;margin-bottom:6px;align-items:center;';
            
            const label = document.createElement('label');
            label.textContent = `Msg ${idx + 1}: ${msg.substring(0, 30)}${msg.length > 30 ? '...' : ''}`;
            label.style.cssText = 'flex:1;';
            
            const input = document.createElement('input');
            input.type = 'number';
            input.min = '1';
            input.value = savedIntervals[String(idx)] || '3';
            input.style.cssText = 'width:80px;';
            input.addEventListener('change', () => savePerMessageTimings());
            input.dataset.index = idx;
            
            div.appendChild(label);
            div.appendChild(input);
            container.appendChild(div);
        });
    } catch (error) {
        console.error('Error loading per-message timings:', error);
    }
}

async function savePerMessageTimings() {
    const inputs = document.querySelectorAll('#per_message_timing_container input');
    const intervals = {};
    inputs.forEach(input => {
        intervals[input.dataset.index] = parseInt(input.value) || 3;
    });
    
    try {
        await fetch('/save_per_message_intervals', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intervals })
        });
    } catch (error) {
        console.error('Error saving timings:', error);
    }
}

async function loadMessageWeights() {
    const container = document.getElementById('message_weights_container');
    if (!container) return;
    
    try {
        const response = await fetch('/status');
        const data = await response.json();
        customMessages = data.custom_texts || [];
        const savedWeights = data.weighted_messages || {};
        
        container.innerHTML = '';
        
        customMessages.forEach((msg, idx) => {
            const div = document.createElement('div');
            div.style.cssText = 'display:flex;gap:8px;margin-bottom:6px;align-items:center;';
            
            const label = document.createElement('label');
            label.textContent = `Msg ${idx + 1}: ${msg.substring(0, 30)}${msg.length > 30 ? '...' : ''}`;
            label.style.cssText = 'flex:1;';
            
            const input = document.createElement('input');
            input.type = 'number';
            input.min = '1';
            input.value = savedWeights[String(idx)] || '1';
            input.style.cssText = 'width:80px;';
            input.dataset.index = idx;
            input.addEventListener('change', async () => {
                await fetch('/set_message_weight', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        index: parseInt(input.dataset.index), 
                        weight: parseInt(input.value) 
                    })
                });
            });
            
            div.appendChild(label);
            div.appendChild(input);
            container.appendChild(div);
        });
    } catch (error) {
        console.error('Error loading message weights:', error);
    }
}

async function toggleChatbox() {
    try {
        await fetch('/toggle_chatbox', { method: 'POST' });
        await updateStatus();
    } catch (error) {
        console.error('Error:', error);
    }
}

async function toggleTime() {
    try {
        await fetch('/toggle_time', { method: 'POST' });
        await updateStatus();
    } catch (error) {
        console.error('Error:', error);
    }
}

async function toggleCustom() {
    try {
        await fetch('/toggle_custom', { method: 'POST' });
        await updateStatus();
    } catch (error) {
        console.error('Error:', error);
    }
}

async function toggleMusic() {
    try {
        await fetch('/toggle_music', { method: 'POST' });
        await updateStatus();
    } catch (error) {
        console.error('Error:', error);
    }
}

async function toggleMusicProgress() {
    try {
        await fetch('/toggle_music_progress', { method: 'POST' });
        await updateStatus();
    } catch (error) {
        console.error('Error:', error);
    }
}

async function toggleWindow() {
    try {
        await fetch('/toggle_window_tracking', { method: 'POST' });
        await updateStatus();
    } catch (error) {
        console.error('Error:', error);
    }
}

async function toggleHeartRate() {
    try {
        await fetch('/toggle_heartrate', { method: 'POST' });
        await updateStatus();
    } catch (error) {
        console.error('Error:', error);
    }
}

async function toggleWeather() {
    try {
        await fetch('/toggle_weather', { method: 'POST' });
        await updateStatus();
    } catch (error) {
        console.error('Error:', error);
    }
}

async function toggleSlimChatbox() {
    try {
        const response = await fetch('/toggle_slim_chatbox', { method: 'POST' });
        const data = await response.json();
        const btn = document.getElementById('btn_slim_chatbox');
        if (btn) {
            btn.className = data.slim_chatbox ? 'btn-on' : 'btn-off';
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

function applyPremiumStyling(customBackground, customButtonColor) {
    if (customBackground) {
        if (customBackground.startsWith('http') || customBackground.startsWith('https')) {
            document.body.style.backgroundImage = `url(${customBackground})`;
            document.body.style.backgroundSize = 'cover';
            document.body.style.backgroundPosition = 'center';
        } else if (customBackground.startsWith('#')) {
            document.body.style.backgroundColor = customBackground;
            document.body.style.backgroundImage = 'none';
        }
    }
    
    if (customButtonColor && customButtonColor.startsWith('#')) {
        const btnOns = document.querySelectorAll('.btn-on');
        btnOns.forEach(btn => {
            btn.style.background = `linear-gradient(135deg, ${customButtonColor}, ${customButtonColor}dd)`;
        });
    }
}

async function updateStatus() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        
        document.getElementById('chatbox_status').textContent = data.chatbox ? 'ON' : 'OFF';
        document.getElementById('time_status').textContent = data.time_on ? data.time : 'OFF';
        document.getElementById('custom_status').textContent = data.custom_on ? data.custom : 'OFF';
        document.getElementById('song_status').textContent = data.music_on ? data.song : 'OFF';
        document.getElementById('window_status').textContent = data.window_on ? data.window : 'OFF';
        document.getElementById('heartrate_status').textContent = data.heartrate_on ? data.heartrate : 'OFF';
        document.getElementById('weather_status').textContent = data.weather_on ? data.weather : 'OFF';
        document.getElementById('last_msg').textContent = data.last_message || '---';
        document.getElementById('preview').textContent = data.preview || 'Preview will show here.';
        
        const albumArt = document.getElementById('album_art');
        if (data.album_art) {
            albumArt.src = data.album_art;
        } else {
            albumArt.src = '';
        }
        
        const queueContainer = document.getElementById('message_queue');
        if (queueContainer && data.message_queue) {
            queueContainer.innerHTML = '';
            data.message_queue.forEach((msg, idx) => {
                const item = document.createElement('div');
                item.textContent = `${idx + 1}. ${msg}`;
                queueContainer.appendChild(item);
            });
        }
        
        updateButton('btn_chatbox', data.chatbox);
        updateButton('btn_time', data.time_on);
        updateButton('btn_custom', data.custom_on);
        updateButton('btn_music', data.music_on);
        updateButton('btn_window', data.window_on);
        updateButton('btn_heartrate', data.heartrate_on);
        updateButton('btn_weather', data.weather_on);
        updateButton('btn_slim_chatbox', data.slim_chatbox);
        updateButton('btn_music_progress', data.music_progress);
        updateButton('btn_system_stats', data.system_stats_enabled);
        updateButton('btn_afk', data.afk_enabled);
        
        const hrSimBtn = document.getElementById('toggle_hr_simulator_btn');
        if (hrSimBtn) {
            hrSimBtn.className = data.hr_simulator_enabled ? 'btn-on' : 'btn-off';
            hrSimBtn.textContent = `HR Simulator: ${data.hr_simulator_enabled ? 'ON' : 'OFF'}`;
        }
        
        const hrTrackingBtn = document.getElementById('toggle_heart_rate_enabled_btn');
        if (hrTrackingBtn) {
            hrTrackingBtn.className = data.heart_rate_enabled ? 'btn-on' : 'btn-off';
            hrTrackingBtn.textContent = `Heart Rate Tracking: ${data.heart_rate_enabled ? 'ON' : 'OFF'}`;
        }
        
        const systemStatsLine = document.getElementById('system_stats_line');
        const systemStatsStatus = document.getElementById('system_stats_status');
        if (systemStatsLine && systemStatsStatus) {
            if (data.system_stats_enabled && data.system_stats) {
                systemStatsLine.style.display = 'block';
                const stats = data.system_stats;
                let statsText = [];
                if (stats.cpu_percent !== undefined) statsText.push(`CPU: ${stats.cpu_percent}%`);
                if (stats.ram_percent !== undefined) statsText.push(`RAM: ${stats.ram_percent}%`);
                if (stats.gpu_available && stats.gpu_percent !== undefined) statsText.push(`GPU: ${stats.gpu_percent}%`);
                systemStatsStatus.textContent = statsText.join(' | ') || 'Loading...';
            } else {
                systemStatsLine.style.display = 'none';
            }
        }
        
        const afkLine = document.getElementById('afk_status_line');
        const afkStatus = document.getElementById('afk_status');
        const afkCountdown = document.getElementById('afk_countdown');
        if (afkLine && afkStatus) {
            if (data.afk_enabled) {
                afkLine.style.display = 'block';
                afkStatus.textContent = data.is_afk ? data.afk_message : 'Active';
                if (afkCountdown) {
                    if (data.is_afk) {
                        afkCountdown.textContent = '';
                    } else if (data.afk_countdown_formatted) {
                        afkCountdown.textContent = `(AFK in ${data.afk_countdown_formatted})`;
                    }
                }
            } else {
                afkLine.style.display = 'none';
                if (afkCountdown) afkCountdown.textContent = '';
            }
        }
        
        const msgLengthWarning = document.getElementById('msg_length_warning');
        const msgLengthText = document.getElementById('msg_length_text');
        if (msgLengthWarning && msgLengthText && data.preview) {
            const previewLen = data.preview.length;
            if (previewLen > 130) {
                msgLengthWarning.style.display = 'block';
                msgLengthText.textContent = `Message length: ${previewLen}/144 chars - some content may be truncated`;
            } else {
                msgLengthWarning.style.display = 'none';
            }
        }
        
        const hrStatsLine = document.getElementById('hr_stats_line');
        const hrStatsText = document.getElementById('hr_stats_text');
        if (hrStatsLine && hrStatsText && data.hr_stats && data.hr_stats.samples >= 5) {
            hrStatsLine.style.display = 'block';
            const trend = data.hr_stats.trend === 'rising' ? ' 📈' : (data.hr_stats.trend === 'falling' ? ' 📉' : '');
            hrStatsText.textContent = `Min: ${data.hr_stats.session_min} | Avg: ${data.hr_stats.session_avg} | Max: ${data.hr_stats.session_max}${trend}`;
        } else if (hrStatsLine) {
            hrStatsLine.style.display = 'none';
        }
        
        if (data.theme) {
            let classes = [];
            if (data.theme === 'light') classes.push('light');
            if (data.compact_mode) classes.push('compact');
            document.body.className = classes.join(' ');
        }

        updateBodyTrackingStatus(data.fbt, data.osc_router, data.fbt_settings);
        
        updateDisplayOptionButtons();
        
    } catch (error) {
        console.error('Error updating status:', error);
    }
}

function updateBodyTrackingStatus(fbt, router, fbtSettings) {
    const activeId = document.activeElement && document.activeElement.id ? document.activeElement.id : '';
    const editingFbtField = activeId.startsWith('fbt_');
    if (fbtSettings && (!fbtSettingsHydrated || (!fbtSettingsDirty && !editingFbtField))) {
        applyFbtSettings(fbtSettings);
        fbtSettingsHydrated = true;
    }
    const fbtBadge = document.getElementById('fbt_status_badge');
    const fbtInfo = document.getElementById('fbt_process_info');
    const fbtLogs = document.getElementById('fbt_logs');
    if (fbtBadge) {
        const running = !!(fbt && fbt.running);
        fbtBadge.textContent = running ? 'Running' : 'Stopped';
        fbtBadge.classList.toggle('status-on', running);
        fbtBadge.classList.toggle('status-off', !running);
    }
    if (fbtInfo) {
        if (fbt && fbt.running) {
            const mode = fbt.mode ? ` (${fbt.mode.toUpperCase()})` : '';
            fbtInfo.textContent = `PID ${fbt.pid}${mode}`;
        } else if (fbt && typeof fbt.exit_code === 'number') {
            fbtInfo.textContent = `Exited with code ${fbt.exit_code}`;
        } else {
            fbtInfo.textContent = '';
        }
    }
    if (fbtLogs) {
        const logs = (fbt && Array.isArray(fbt.logs) && fbt.logs.length > 0) ? fbt.logs.join('\n') : 'No logs yet.';
        fbtLogs.textContent = logs;
        fbtLogs.scrollTop = fbtLogs.scrollHeight;
    }

    const routerBadge = document.getElementById('router_status_badge');
    const routerLogs = document.getElementById('router_logs');
    if (routerBadge) {
        const running = !!(router && router.running);
        routerBadge.textContent = running ? 'Running' : 'Stopped';
        routerBadge.classList.toggle('status-on', running);
        routerBadge.classList.toggle('status-off', !running);
    }
    if (routerLogs) {
        const logs = (router && Array.isArray(router.logs) && router.logs.length > 0) ? router.logs.join('\n') : 'No logs yet.';
        routerLogs.textContent = logs;
        routerLogs.scrollTop = routerLogs.scrollHeight;
    }
}

async function updateDisplayOptionButtons() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        
        const themeBtn = document.getElementById('toggle_theme_btn');
        const streamerBtn = document.getElementById('toggle_streamer_btn');
        const compactBtn = document.getElementById('toggle_compact_btn');
        
        if (themeBtn) {
            themeBtn.className = data.theme === 'light' ? 'btn-on' : 'btn-off';
            themeBtn.textContent = `Theme: ${data.theme === 'light' ? 'Light' : 'Dark'}`;
        }
        
        if (streamerBtn) {
            streamerBtn.className = data.streamer_mode ? 'btn-on' : 'btn-off';
            streamerBtn.textContent = `Streamer Mode: ${data.streamer_mode ? 'ON' : 'OFF'}`;
        }
        
        if (compactBtn) {
            compactBtn.className = data.compact_mode ? 'btn-on' : 'btn-off';
            compactBtn.textContent = `Compact Mode: ${data.compact_mode ? 'ON' : 'OFF'}`;
        }
    } catch (error) {
        console.error('Error updating display buttons:', error);
    }
}

function updateButton(id, isOn) {
    const btn = document.getElementById(id);
    if (btn) {
        btn.className = isOn ? 'btn-on' : 'btn-off';
    }
}

function startUpdate() {
    updateStatus();
    if (updateTimer) clearInterval(updateTimer);
    updateTimer = setInterval(updateStatus, refreshInterval * 1000);
}

function setupLayout() {
    const list = document.getElementById('layout_list');
    let draggedItem = null;

    list.addEventListener('dragstart', (e) => {
        draggedItem = e.target;
        e.target.style.opacity = '0.5';
    });

    list.addEventListener('dragend', (e) => {
        e.target.style.opacity = '1';
    });

    list.addEventListener('dragover', (e) => {
        e.preventDefault();
        const afterElement = getDragAfterElement(list, e.clientY);
        if (afterElement == null) {
            list.appendChild(draggedItem);
        } else {
            list.insertBefore(draggedItem, afterElement);
        }
    });

    list.addEventListener('drop', async (e) => {
        e.preventDefault();
        const items = Array.from(list.querySelectorAll('.layout-item'));
        const order = items.map(item => item.dataset.key);
        
        try {
            await fetch('/save_layout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ layout_order: order })
            });
        } catch (error) {
            console.error('Error saving layout:', error);
        }
    });
}

function getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.layout-item:not(.dragging)')];
    
    return draggableElements.reduce((closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        
        if (offset < 0 && offset > closest.offset) {
            return { offset: offset, element: child };
        } else {
            return closest;
        }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
}

const manualMsgForm = document.getElementById('manual_msg_form');
if (manualMsgForm) {
    manualMsgForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        try {
            const response = await fetch('/send', {
                method: 'POST',
                body: formData
            });
            if (response.ok) {
                e.target.reset();
                await updateStatus();
            }
        } catch (error) {
            console.error('Error sending message:', error);
        }
    });
}
