(function () {
    'use strict';

    const SETTINGS_KEY = 'aurora_audio_quality_settings_v1';
    const LOUDNESS_CACHE_KEY = 'aurora_loudness_cache_v1';
    const ANALYSIS_VERSION = 2;
    const TARGET_LUFS = -18;
    const LUFS_OFFSET = -0.691;
    const ABSOLUTE_GATE_LUFS = -70;
    const RELATIVE_GATE_LU = -10;
    const MAX_GAIN_DB = 8;
    const MIN_GAIN_DB = -12;
    const TRUE_PEAK_CEILING_DBTP = -1;
    const LOUDNESS_SEGMENT_SECONDS = 0.1;
    const LOUDNESS_BLOCK_SEGMENTS = 4;
    const METER_BUFFER_SIZE = 2048;
    const MIN_NATURAL_END_SECONDS = 3;
    const NATURAL_END_COVERAGE = 0.8;
    const MANUAL_MIN_SECONDS = 60;
    const MANUAL_MIN_COVERAGE = 0.5;
    const MAX_CACHE_ENTRIES = 500;

    const DEFAULT_SETTINGS = Object.freeze({
        normalization: true,
        peakProtection: true,
        preloadNext: true,
        smoothTransitions: true,
        transitionMs: 120,
    });

    function readStoredValue(key) {
        try {
            if (window.electronAPI?.getStorageItem) {
                const persisted = window.electronAPI.getStorageItem(key);
                if (persisted !== null && persisted !== undefined) return persisted;
            }
            return window.localStorage.getItem(key);
        } catch (error) {
            console.warn('[AudioQuality] Could not read settings', error);
            return null;
        }
    }

    function writeStoredValue(key, value) {
        try {
            window.localStorage.setItem(key, String(value));
            window.electronAPI?.setStorageItem?.(key, value);
        } catch (error) {
            console.warn('[AudioQuality] Could not save settings', error);
        }
    }

    function readJson(key, fallback) {
        const raw = readStoredValue(key);
        if (!raw) return fallback;
        try {
            return JSON.parse(raw);
        } catch (error) {
            return fallback;
        }
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function dbToGain(db) {
        return Math.pow(10, db / 20);
    }

    function gainToDb(gain) {
        return gain > 0 ? 20 * Math.log10(gain) : -Infinity;
    }

    function energyToLufs(energy) {
        return energy > 0 ? LUFS_OFFSET + 10 * Math.log10(energy) : -Infinity;
    }

    function cubicInterpolate(p0, p1, p2, p3, t) {
        const t2 = t * t;
        const t3 = t2 * t;
        return 0.5 * (
            (2 * p1)
            + (-p0 + p2) * t
            + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
            + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
        );
    }

    function trackCacheKey(url, songId) {
        if (songId !== null && songId !== undefined && songId !== '') {
            return `song:${songId}`;
        }
        try {
            return `path:${new URL(url, window.location.origin).pathname}`;
        } catch (error) {
            return `url:${url}`;
        }
    }

    function fingerprintModifiedAt(fingerprint) {
        const separator = String(fingerprint || '').lastIndexOf(':');
        if (separator < 0) return null;
        const modifiedNs = Number(String(fingerprint).slice(separator + 1));
        const modifiedAt = modifiedNs / 1e6;
        return Number.isFinite(modifiedAt) ? modifiedAt : null;
    }

    class AudioQualityEngine {
        constructor(mediaElement) {
            this.media = mediaElement;
            this.settings = {
                ...DEFAULT_SETTINGS,
                ...readJson(SETTINGS_KEY, {}),
            };
            this.loudnessCache = readJson(LOUDNESS_CACHE_KEY, {});
            this.userVolume = Number.isFinite(mediaElement.volume) ? mediaElement.volume : 0.8;
            this.context = null;
            this.sourceNode = null;
            this.analysisHighPassNode = null;
            this.analysisShelfNode = null;
            this.loudnessMeterNode = null;
            this.rawPeakMeterNode = null;
            this.analysisSinkNode = null;
            this.rawPeakSinkNode = null;
            this.trackGainNode = null;
            this.transitionGainNode = null;
            this.masterGainNode = null;
            this.limiterNode = null;
            this.currentTrack = null;
            this.pendingMetadata = new Map();
            this.preloader = new Audio();
            this.preloader.preload = 'auto';
            this.preloadedUrl = '';
            this.operationToken = 0;

            const activate = () => this.ensureGraph();
            document.addEventListener('pointerdown', activate, { capture: true, once: true });
            document.addEventListener('keydown', activate, { capture: true, once: true });
            document.addEventListener('DOMContentLoaded', () => this.bindSettingsUI());
        }

        ensureGraph() {
            if (this.context) {
                if (this.context.state === 'suspended') this.context.resume().catch(() => {});
                return this.context;
            }

            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) return null;

            try {
                this.context = new AudioContextClass();
                this.sourceNode = this.context.createMediaElementSource(this.media);
                this.analysisHighPassNode = this.context.createBiquadFilter();
                this.analysisShelfNode = this.context.createBiquadFilter();
                this.loudnessMeterNode = this.context.createScriptProcessor(METER_BUFFER_SIZE, 2, 1);
                this.rawPeakMeterNode = this.context.createScriptProcessor(METER_BUFFER_SIZE, 2, 1);
                this.analysisSinkNode = this.context.createGain();
                this.rawPeakSinkNode = this.context.createGain();
                this.trackGainNode = this.context.createGain();
                this.transitionGainNode = this.context.createGain();
                this.masterGainNode = this.context.createGain();
                this.limiterNode = this.context.createDynamicsCompressor();

                // K-weighting branch for integrated loudness. It is analysis-only.
                this.analysisHighPassNode.type = 'highpass';
                this.analysisHighPassNode.frequency.value = 38.1358;
                this.analysisHighPassNode.Q.value = 0.5003;
                this.analysisShelfNode.type = 'highshelf';
                this.analysisShelfNode.frequency.value = 1681.974;
                this.analysisShelfNode.gain.value = 4;
                this.analysisSinkNode.gain.value = 0;
                this.rawPeakSinkNode.gain.value = 0;
                this.loudnessMeterNode.onaudioprocess = event => this.captureLoudness(event.inputBuffer);
                this.rawPeakMeterNode.onaudioprocess = event => this.captureTruePeak(event.inputBuffer);

                this.sourceNode.connect(this.trackGainNode);
                this.trackGainNode.connect(this.transitionGainNode);
                this.transitionGainNode.connect(this.masterGainNode);
                this.masterGainNode.connect(this.limiterNode);
                this.limiterNode.connect(this.context.destination);
                this.sourceNode.connect(this.analysisHighPassNode);
                this.analysisHighPassNode.connect(this.analysisShelfNode);
                this.analysisShelfNode.connect(this.loudnessMeterNode);
                this.loudnessMeterNode.connect(this.analysisSinkNode);
                this.analysisSinkNode.connect(this.context.destination);
                this.sourceNode.connect(this.rawPeakMeterNode);
                this.rawPeakMeterNode.connect(this.rawPeakSinkNode);
                this.rawPeakSinkNode.connect(this.context.destination);

                this.media.volume = 1;
                this.masterGainNode.gain.value = this.userVolume;
                this.transitionGainNode.gain.value = 1;
                this.configureLimiter();
                this.applyTrackGain(true);
                this.context.resume().catch(() => {});
            } catch (error) {
                console.error('[AudioQuality] Web Audio initialization failed', error);
                this.context = null;
                this.media.volume = this.userVolume;
            }
            return this.context;
        }

        configureLimiter() {
            if (!this.limiterNode) return;
            const enabled = this.settings.normalization && this.settings.peakProtection;
            this.limiterNode.threshold.value = enabled ? TRUE_PEAK_CEILING_DBTP : 0;
            this.limiterNode.knee.value = 0;
            this.limiterNode.ratio.value = enabled ? 20 : 1;
            this.limiterNode.attack.value = 0.003;
            this.limiterNode.release.value = 0.12;
        }

        getSettings() {
            return { ...this.settings };
        }

        setSetting(name, value) {
            if (!(name in DEFAULT_SETTINGS)) return;
            this.settings[name] = typeof DEFAULT_SETTINGS[name] === 'boolean' ? !!value : value;
            writeStoredValue(SETTINGS_KEY, JSON.stringify(this.settings));
            this.configureLimiter();
            this.applyTrackGain(false);
            if (!this.settings.preloadNext) this.clearPreload();
            this.emitStatus();
        }

        setVolume(value, immediate = false) {
            const volume = clamp(Number(value) || 0, 0, 1);
            this.userVolume = volume;
            if (!this.masterGainNode || !this.context) {
                this.media.volume = volume;
                return;
            }
            const now = this.context.currentTime;
            const gain = this.masterGainNode.gain;
            gain.cancelScheduledValues(now);
            gain.setValueAtTime(gain.value, now);
            if (immediate) gain.setValueAtTime(volume, now);
            else gain.linearRampToValueAtTime(volume, now + 0.04);
        }

        getVolume() {
            return this.userVolume;
        }

        needsMetadata(songId) {
            if (songId === null || songId === undefined || songId === '') return false;
            return !this.currentTrack
                || String(this.currentTrack.songId) !== String(songId)
                || !this.currentTrack.metadataLoaded;
        }

        ensureTrack(url, songId) {
            const key = trackCacheKey(url, songId);
            if (!this.currentTrack || this.currentTrack.key !== key) {
                this.beginTrack(url, songId);
            }
        }

        beginTrack(url, songId, replayGain = null, fingerprint = null) {
            const key = trackCacheKey(url, songId);
            if (this.currentTrack?.key !== key) this.finishTrack();
            this.currentTrack = {
                key,
                url,
                songId: songId === null || songId === undefined ? null : String(songId),
                replayGain,
                fingerprint,
                metadataLoaded: !!(replayGain || fingerprint),
                loudnessBlocks: [],
                loudnessWindow: [],
                segmentEnergy: 0,
                segmentFrames: 0,
                truePeak: 0,
                truePeakHistory: [],
                sampledSeconds: new Set(),
                lastMediaTime: null,
                duration: 0,
                naturalEnd: false,
            };
            const pendingMetadata = this.currentTrack.songId === null
                ? null
                : this.pendingMetadata.get(this.currentTrack.songId);
            if (pendingMetadata) {
                this.pendingMetadata.delete(this.currentTrack.songId);
                this.setAudioQualityMetadata(this.currentTrack.songId, pendingMetadata);
            } else {
                this.applyTrackGain(true);
            }
        }

        completeAndRestartTrack(url, songId) {
            const replayGain = this.currentTrack?.replayGain || null;
            const fingerprint = this.currentTrack?.fingerprint || null;
            this.finishTrack();
            this.beginTrack(url, songId, replayGain, fingerprint);
        }

        markTrackEnded() {
            if (this.currentTrack) this.currentTrack.naturalEnd = true;
        }

        relearnCurrentTrack() {
            if (!this.currentTrack) return;
            delete this.loudnessCache[this.currentTrack.key];
            writeStoredValue(LOUDNESS_CACHE_KEY, JSON.stringify(this.loudnessCache));
            this.currentTrack.replayGain = null;
            this.currentTrack.loudnessBlocks = [];
            this.currentTrack.loudnessWindow = [];
            this.currentTrack.segmentEnergy = 0;
            this.currentTrack.segmentFrames = 0;
            this.currentTrack.truePeak = 0;
            this.currentTrack.truePeakHistory = [];
            this.currentTrack.sampledSeconds = new Set();
            this.currentTrack.lastMediaTime = null;
            this.currentTrack.duration = Number.isFinite(this.media.duration) ? this.media.duration : 0;
            this.currentTrack.naturalEnd = false;
            this.applyTrackGain(false);
        }

        setAudioQualityMetadata(songId, metadata) {
            const metadataSongId = String(songId);
            if (!this.currentTrack || String(this.currentTrack.songId) !== metadataSongId) {
                this.pendingMetadata.set(metadataSongId, metadata || {});
                return;
            }
            const fingerprint = metadata?.fingerprint || null;
            let cached = this.loudnessCache[this.currentTrack.key];
            let cacheChanged = false;
            if (cached && Number(cached.analysisVersion) !== ANALYSIS_VERSION) {
                delete this.loudnessCache[this.currentTrack.key];
                cached = null;
                cacheChanged = true;
            }
            if (cached && fingerprint) {
                if (!cached.fingerprint) {
                    const fileModifiedAt = fingerprintModifiedAt(fingerprint);
                    const learnedAt = Number(cached.updatedAt);
                    if (fileModifiedAt !== null && Number.isFinite(learnedAt) && learnedAt >= fileModifiedAt) {
                        cached.fingerprint = fingerprint;
                    } else {
                        delete this.loudnessCache[this.currentTrack.key];
                    }
                    cacheChanged = true;
                } else if (cached.fingerprint !== fingerprint) {
                    delete this.loudnessCache[this.currentTrack.key];
                    cacheChanged = true;
                }
            }
            if (cacheChanged) {
                writeStoredValue(LOUDNESS_CACHE_KEY, JSON.stringify(this.loudnessCache));
            }
            if (fingerprint) this.currentTrack.fingerprint = fingerprint;
            this.currentTrack.replayGain = metadata?.replaygain || null;
            this.currentTrack.metadataLoaded = true;
            this.applyTrackGain(false);
        }

        resolvedTrackGain() {
            if (!this.currentTrack) {
                return { gainDb: 0, statusGainDb: null, mode: 'No Track' };
            }

            const tagged = this.currentTrack.replayGain;
            const cached = this.loudnessCache[this.currentTrack.key];
            const learned = Number(cached?.analysisVersion) === ANALYSIS_VERSION
                && cached?.fingerprint
                && this.currentTrack.fingerprint
                && cached.fingerprint === this.currentTrack.fingerprint
                ? cached
                : null;
            let gainDb = Number(tagged?.gain_db);
            let peak = Number(tagged?.peak);
            let mode = 'ReplayGain';

            if (!Number.isFinite(gainDb)) {
                gainDb = Number(learned?.gainDb);
                peak = Number(learned?.truePeak ?? learned?.peak);
                mode = Number.isFinite(gainDb) ? 'Learned' : 'Learning';
            }
            if (!Number.isFinite(gainDb)) gainDb = 0;

            gainDb = clamp(gainDb, MIN_GAIN_DB, MAX_GAIN_DB);
            if (this.settings.peakProtection && Number.isFinite(peak) && peak > 0) {
                const peakSafeGainDb = TRUE_PEAK_CEILING_DBTP - gainToDb(peak);
                gainDb = Math.min(gainDb, peakSafeGainDb);
            }
            return {
                gainDb: this.settings.normalization ? gainDb : 0,
                statusGainDb: gainDb,
                mode,
            };
        }

        applyTrackGain(immediate) {
            const result = this.resolvedTrackGain();
            if (this.trackGainNode && this.context) {
                const target = dbToGain(result.gainDb);
                const now = this.context.currentTime;
                const gain = this.trackGainNode.gain;
                gain.cancelScheduledValues(now);
                gain.setValueAtTime(gain.value, now);
                if (immediate) gain.setValueAtTime(target, now);
                else gain.linearRampToValueAtTime(target, now + 0.6);
            }
            this.emitStatus(result);
        }

        canCaptureTrack(track) {
            return !!track
                && !this.media.paused
                && !this.media.seeking
                && this.media.readyState >= 2
                && (track.replayGain?.gain_db === undefined || track.replayGain?.gain_db === null);
        }

        captureLoudness(inputBuffer) {
            const track = this.currentTrack;
            if (!this.canCaptureTrack(track)) return;

            const currentTime = Number(this.media.currentTime);
            if (Number.isFinite(currentTime)) {
                if (track.lastMediaTime !== null && Math.abs(currentTime - track.lastMediaTime) > 0.75) {
                    track.loudnessWindow = [];
                    track.segmentEnergy = 0;
                    track.segmentFrames = 0;
                }
                track.lastMediaTime = currentTime;
                track.sampledSeconds.add(Math.floor(currentTime));
            }
            if (Number.isFinite(this.media.duration)) track.duration = this.media.duration;

            const channelCount = Math.min(inputBuffer.numberOfChannels, 2);
            if (!channelCount) return;
            const channels = [];
            for (let channel = 0; channel < channelCount; channel += 1) {
                channels.push(inputBuffer.getChannelData(channel));
            }

            const sampleRate = Number(inputBuffer.sampleRate) || Number(this.context?.sampleRate) || 48000;
            const segmentFrameTarget = Math.max(1, Math.round(sampleRate * LOUDNESS_SEGMENT_SECONDS));
            for (let frame = 0; frame < inputBuffer.length; frame += 1) {
                let frameEnergy = 0;
                for (let channel = 0; channel < channelCount; channel += 1) {
                    const sample = channels[channel][frame];
                    frameEnergy += sample * sample;
                }
                track.segmentEnergy += frameEnergy;
                track.segmentFrames += 1;

                if (track.segmentFrames >= segmentFrameTarget) {
                    const segment = {
                        energy: track.segmentEnergy,
                        frames: track.segmentFrames,
                    };
                    track.loudnessWindow.push(segment);
                    if (track.loudnessWindow.length >= LOUDNESS_BLOCK_SEGMENTS) {
                        const blockEnergy = track.loudnessWindow.reduce((sum, item) => sum + item.energy, 0);
                        const blockFrames = track.loudnessWindow.reduce((sum, item) => sum + item.frames, 0);
                        if (blockFrames > 0 && blockEnergy > 0) {
                            track.loudnessBlocks.push(blockEnergy / blockFrames);
                        }
                        track.loudnessWindow.shift();
                    }
                    track.segmentEnergy = 0;
                    track.segmentFrames = 0;
                }
            }
        }

        captureTruePeak(inputBuffer) {
            const track = this.currentTrack;
            if (!this.canCaptureTrack(track)) return;

            const channelCount = Math.min(inputBuffer.numberOfChannels, 2);
            for (let channel = 0; channel < channelCount; channel += 1) {
                const data = inputBuffer.getChannelData(channel);
                const history = track.truePeakHistory[channel] || [];
                const samples = new Float32Array(history.length + data.length);
                samples.set(history, 0);
                samples.set(data, history.length);

                for (let index = 0; index < samples.length; index += 1) {
                    track.truePeak = Math.max(track.truePeak, Math.abs(samples[index]));
                }
                for (let index = 0; index <= samples.length - 4; index += 1) {
                    const p0 = samples[index];
                    const p1 = samples[index + 1];
                    const p2 = samples[index + 2];
                    const p3 = samples[index + 3];
                    track.truePeak = Math.max(
                        track.truePeak,
                        Math.abs(cubicInterpolate(p0, p1, p2, p3, 0.25)),
                        Math.abs(cubicInterpolate(p0, p1, p2, p3, 0.5)),
                        Math.abs(cubicInterpolate(p0, p1, p2, p3, 0.75)),
                    );
                }
                track.truePeakHistory[channel] = Array.from(samples.slice(-3));
            }
        }

        finishTrack() {
            const track = this.currentTrack;
            if (!track || track.replayGain?.gain_db !== undefined && track.replayGain?.gain_db !== null) {
                this.currentTrack = null;
                return;
            }
            const blocks = Array.from(track.loudnessBlocks || []).filter(value => Number.isFinite(value) && value > 0);
            const coveredSeconds = track.sampledSeconds?.size || 0;
            const duration = Number(track.duration) || 0;
            const coverage = duration > 0 ? Math.min(1, coveredSeconds / duration) : 0;
            const naturalEndEligible = track.naturalEnd
                && coveredSeconds >= MIN_NATURAL_END_SECONDS
                && coverage >= NATURAL_END_COVERAGE;
            const manualEligible = coveredSeconds >= MANUAL_MIN_SECONDS
                && coverage >= MANUAL_MIN_COVERAGE;
            if (!naturalEndEligible && !manualEligible) {
                this.currentTrack = null;
                return;
            }

            const absoluteGated = blocks.filter(value => energyToLufs(value) >= ABSOLUTE_GATE_LUFS);
            if (!absoluteGated.length) {
                this.currentTrack = null;
                return;
            }
            const ungatedMean = absoluteGated.reduce((sum, value) => sum + value, 0) / absoluteGated.length;
            const relativeGateLufs = Math.max(ABSOLUTE_GATE_LUFS, energyToLufs(ungatedMean) + RELATIVE_GATE_LU);
            const gated = absoluteGated.filter(value => energyToLufs(value) >= relativeGateLufs);
            if (!gated.length) {
                this.currentTrack = null;
                return;
            }
            const gatedMean = gated.reduce((sum, value) => sum + value, 0) / gated.length;
            const measuredLufs = energyToLufs(gatedMean);
            const gainDb = clamp(TARGET_LUFS - measuredLufs, MIN_GAIN_DB, MAX_GAIN_DB);
            const truePeak = Number(track.truePeak) || 0;

            this.loudnessCache[track.key] = {
                analysisVersion: ANALYSIS_VERSION,
                algorithm: 'bs1770-k-gated',
                gainDb,
                peak: truePeak,
                truePeak,
                truePeakDbtp: truePeak > 0 ? gainToDb(truePeak) : null,
                truePeakMethod: '4x-cubic',
                measuredLufs,
                measuredDb: measuredLufs,
                targetLufs: TARGET_LUFS,
                fingerprint: track.fingerprint,
                coveredSeconds,
                coverage,
                blockCount: blocks.length,
                gatedBlockCount: gated.length,
                confidence: naturalEndEligible ? 'full' : 'partial',
                updatedAt: Date.now(),
            };
            const entries = Object.entries(this.loudnessCache)
                .sort((a, b) => (b[1].updatedAt || 0) - (a[1].updatedAt || 0))
                .slice(0, MAX_CACHE_ENTRIES);
            this.loudnessCache = Object.fromEntries(entries);
            writeStoredValue(LOUDNESS_CACHE_KEY, JSON.stringify(this.loudnessCache));
            this.currentTrack = null;
        }

        async fadeTransitionTo(value, durationMs) {
            if (!this.transitionGainNode || !this.context || durationMs <= 0) return;
            const now = this.context.currentTime;
            const gain = this.transitionGainNode.gain;
            gain.cancelScheduledValues(now);
            gain.setValueAtTime(gain.value, now);
            gain.linearRampToValueAtTime(value, now + durationMs / 1000);
            await new Promise(resolve => window.setTimeout(resolve, durationMs));
        }

        async play(fade = true) {
            const token = ++this.operationToken;
            this.ensureGraph();
            if (this.context?.state === 'suspended') await this.context.resume().catch(() => {});
            const shouldFade = fade && this.settings.smoothTransitions && !!this.transitionGainNode;
            if (shouldFade) this.transitionGainNode.gain.value = 0;
            try {
                await this.media.play();
                if (token !== this.operationToken) return;
                if (shouldFade) await this.fadeTransitionTo(1, this.settings.transitionMs);
            } catch (error) {
                if (shouldFade) this.transitionGainNode.gain.value = 1;
                throw error;
            }
        }

        async pause(fade = true) {
            const token = ++this.operationToken;
            const shouldFade = fade && this.settings.smoothTransitions && !!this.transitionGainNode;
            if (shouldFade) await this.fadeTransitionTo(0, this.settings.transitionMs);
            if (token !== this.operationToken) return;
            this.media.pause();
            if (this.transitionGainNode) this.transitionGainNode.gain.value = 1;
        }

        async toggle() {
            if (this.media.paused) return this.play(true);
            return this.pause(true);
        }

        async transitionTo(url, songId, autoPlay) {
            const token = ++this.operationToken;
            this.ensureGraph();
            const wasPlaying = !this.media.paused;
            if (wasPlaying && this.settings.smoothTransitions && this.transitionGainNode) {
                await this.fadeTransitionTo(0, this.settings.transitionMs);
            }
            if (token !== this.operationToken) return;

            this.media.pause();
            this.media.src = url;
            this.media.load();
            this.beginTrack(url, songId);
            if (this.transitionGainNode) this.transitionGainNode.gain.value = autoPlay ? 0 : 1;

            if (!autoPlay) return;
            try {
                await this.media.play();
                if (token !== this.operationToken) return;
                if (this.settings.smoothTransitions && this.transitionGainNode) {
                    await this.fadeTransitionTo(1, this.settings.transitionMs);
                } else if (this.transitionGainNode) {
                    this.transitionGainNode.gain.value = 1;
                }
            } catch (error) {
                if (this.transitionGainNode) this.transitionGainNode.gain.value = 1;
                throw error;
            }
        }

        preloadTrack(url) {
            if (!this.settings.preloadNext || !url) return;
            const absoluteUrl = new URL(url, window.location.origin).href;
            if (absoluteUrl === this.preloadedUrl) return;
            this.preloadedUrl = absoluteUrl;
            this.preloader.src = absoluteUrl;
            this.preloader.load();
        }

        clearPreload() {
            this.preloadedUrl = '';
            this.preloader.removeAttribute('src');
            this.preloader.load();
        }

        reset() {
            ++this.operationToken;
            this.finishTrack();
            this.clearPreload();
            if (this.transitionGainNode) this.transitionGainNode.gain.value = 1;
            if (this.trackGainNode) this.trackGainNode.gain.value = 1;
        }

        emitStatus(result = this.resolvedTrackGain()) {
            document.dispatchEvent(new CustomEvent('aurora:audio-quality-status', {
                detail: {
                    mode: result.mode,
                    gainDb: result.statusGainDb ?? result.gainDb,
                    normalization: this.settings.normalization,
                    hasTrack: !!this.currentTrack,
                },
            }));
        }

        bindSettingsUI() {
            const button = document.getElementById('audio-quality-btn');
            const panel = document.getElementById('audio-quality-panel');
            const relearnButton = document.getElementById('audio-quality-relearn-btn');
            if (!button || !panel) return;

            panel.querySelectorAll('[data-audio-setting]').forEach(input => {
                const setting = input.dataset.audioSetting;
                input.checked = !!this.settings[setting];
                input.addEventListener('change', () => this.setSetting(setting, input.checked));
            });

            button.addEventListener('click', event => {
                event.stopPropagation();
                panel.classList.toggle('show');
                button.setAttribute('aria-expanded', panel.classList.contains('show') ? 'true' : 'false');
            });
            panel.addEventListener('click', event => event.stopPropagation());
            relearnButton?.addEventListener('click', event => {
                event.stopPropagation();
                this.relearnCurrentTrack();
            });
            document.addEventListener('click', event => {
                if (!event.target.closest('.audio-quality-container')) {
                    panel.classList.remove('show');
                    button.setAttribute('aria-expanded', 'false');
                }
            });
            document.addEventListener('aurora:audio-quality-status', event => {
                const status = document.getElementById('audio-quality-status');
                if (!status) return;
                const detail = event.detail || {};
                const gain = Number(detail.gainDb);
                const gainLabel = Number.isFinite(gain) && Math.abs(gain) >= 0.05
                    ? ` ${gain > 0 ? '+' : ''}${gain.toFixed(1)} dB`
                    : '';
                status.textContent = `${detail.mode || 'Neutral'}${gainLabel}`;
                if (relearnButton) {
                    const canRelearn = detail.mode === 'Learned' || detail.mode === 'ReplayGain';
                    relearnButton.hidden = !canRelearn;
                    relearnButton.disabled = !canRelearn;
                }
            });
            this.emitStatus();
        }
    }

    window.AuroraAudioQuality = {
        create(mediaElement) {
            return new AudioQualityEngine(mediaElement);
        },
    };
})();
