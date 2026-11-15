"""Moteur de Performance DJ Live & Routines de Club pour Kéranos.

Ce moteur implémente de vrais gestes et techniques de DJ professionnel :
1. Vinyl Brake (Turntable Stop réaliste par décélération physique du moteur).
2. Beat Stutter Roll (Roulement de boucle 1/4 -> 1/8 -> 1/16 avec balayage passe-haut).
3. Backspin Rewind (Coup de platine arrière ultra-rapide).
4. Drop-to-Drop / Quick-Mix (Transition directe entre refrains/drops sans attendre 3 minutes).
"""
import sys, time
from pathlib import Path
import numpy as np
from scipy import signal, interpolate

class DJRoutineEngine:
    def __init__(self, target_sr=44100):
        self.target_sr = target_sr

    # =========================================================================
    # EFFET 1 : VINYL BRAKE (TURNTABLE MOTOR STOP)
    # =========================================================================
    def creer_vinyl_brake(self, audio, duree_sec=0.75):
        """
        Simule l'arrêt physique d'une platine vinyle (Turntable Brake).
        La vitesse et le pitch chutent progressivement jusqu'à 0 avec l'inertie du plateau.
        """
        sr = self.target_sr
        n_out = int(duree_sec * sr)
        t = np.linspace(0, 1, n_out)
        
        # Profil de vitesse quadratique décroissant de 1.0 à 0.0
        # v(t) = (1 - t)^2
        # Position source intégrée : phi(t) = t - t^2 + t^3 / 3
        phi = (t - t**2 + (t**3) / 3.0) * (duree_sec * sr * 0.9)
        
        # Interpolation pour échantillonner le signal source
        max_idx = min(len(audio) - 1, int(np.max(phi)) + 1)
        x_indices = np.arange(len(audio))
        
        out = np.zeros((n_out, 2), dtype=np.float32)
        for ch in range(2):
            f_interp = interpolate.interp1d(x_indices, audio[:, ch], kind='linear', bounds_error=False, fill_value=0.0)
            out[:, ch] = f_interp(phi)
            
        # Atténuation douce vers la fin pour éviter tout clic
        envelope = np.clip(1.0 - t**3, 0.0, 1.0)[:, None]
        out *= envelope
        return out

    # =========================================================================
    # EFFET 2 : BEAT STUTTER ROLL (MITRAILLETTE DE BOUCLE & MONTÉE RISER)
    # =========================================================================
    def creer_stutter_roll(self, audio_cue, bpm, nb_beats=2.0):
        """
        Crée une montée de caisse claire / boucle en stutter :
        - 1/4 de temps répété 4 fois
        - 1/8 de temps répété 8 fois
        - Balayage de filtre passe-haut pour faire monter la tension
        """
        sr = self.target_sr
        beat_sec = 60.0 / bpm
        duree_totale = int(nb_beats * beat_sec * sr)
        
        morceau_roll = np.zeros((duree_totale, 2), dtype=np.float32)
        
        # 1er temps : 4 répétitions à 1/4 de beat
        len_quarter = int((beat_sec / 4.0) * sr)
        slice_quarter = audio_cue[-len_quarter:].copy()
        
        pos = 0
        for _ in range(4):
            if pos + len_quarter <= duree_totale:
                morceau_roll[pos:pos+len_quarter] = slice_quarter
                pos += len_quarter
                
        # 2ème temps : 8 répétitions à 1/8 de beat (mitraillette rapide)
        len_eighth = int((beat_sec / 8.0) * sr)
        slice_eighth = audio_cue[-len_eighth:].copy()
        
        while pos + len_eighth <= duree_totale:
            morceau_roll[pos:pos+len_eighth] = slice_eighth
            pos += len_eighth
            
        # Filtre passe-haut montant (Riser)
        # On découpe en 4 segments et on augmente la fréquence de coupure
        seg_len = duree_totale // 4
        cutoffs = [200, 500, 1200, 2400]
        for idx, fc in enumerate(cutoffs):
            deb = idx * seg_len
            fin = min(duree_totale, (idx + 1) * seg_len)
            sos = signal.butter(2, fc / (sr / 2), btype='high', output='sos')
            morceau_roll[deb:fin] = signal.sosfilt(sos, morceau_roll[deb:fin], axis=0)
            
        return morceau_roll

    # =========================================================================
    # EFFET 3 : BACKSPIN (REWIND VINYLE RAPIDE)
    # =========================================================================
    def creer_backspin(self, audio, duree_sec=0.55):
        """
        Simule le coup de platine en arrière (Backspin / Tape Rewind).
        Le vinyle est tourné à l'envers à vitesse accélérée avec un filtre médium.
        """
        sr = self.target_sr
        n_out = int(duree_sec * sr)
        
        # Audio inversé
        extrait = audio[-int(1.5 * sr):][::-1]
        
        t = np.linspace(0, 1, n_out)
        # Vitesse accélérée : phi(t) = t * v_start + t^2 * acc
        phi = (t * 1.5 + (t**2) * 2.5) * (len(extrait) * 0.6)
        
        x_indices = np.arange(len(extrait))
        out = np.zeros((n_out, 2), dtype=np.float32)
        for ch in range(2):
            f_interp = interpolate.interp1d(x_indices, extrait[:, ch], kind='linear', bounds_error=False, fill_value=0.0)
            out[:, ch] = f_interp(phi)
            
        # Filtre passe-bande agressif style vinyle (600Hz - 5000Hz)
        sos = signal.butter(2, [600 / (sr/2), 5000 / (sr/2)], btype='bandpass', output='sos')
        out = signal.sosfilt(sos, out, axis=0)
        
        # Atténuation finale
        env = np.linspace(0.8, 0.05, n_out)[:, None]
        out *= env
        return out

    # =========================================================================
    # ROUTINE COMPLÈTE : QUICK-MIX DROP-TO-DROP (VRAI SET DE CLUB)
    # =========================================================================
    def creer_routine_club(self, piste_a, piste_b, cue_out_a_sec=34.8, cue_in_b_sec=28.5, style_fx="stutter_brake"):
        """
        Génère un véritable set de club :
        - Piste A joue son couplet/refrain jusqu'à cue_out_a_sec (ex: 35s).
        - Transition DJ explosive (au choix : Stutter Roll + Vinyl Brake, ou Backspin).
        - Drop direct sur le refrain percutant de la Piste B à cue_in_b_sec (ex: 28.5s).
        - Piste B continue avec toute son énergie !
        """
        from musique.automix_engine import AutoMixEngine
        aux_engine = AutoMixEngine(self.target_sr)
        
        sr = self.target_sr
        bpm_a = aux_engine.detecter_bpm(piste_a["data"], sr)
        bpm_b = aux_engine.detecter_bpm(piste_b["data"], sr)
        
        beat_sec_a = 60.0 / bpm_a
        
        # 1. Découpage de la Piste A
        idx_cut_a = int(cue_out_a_sec * sr)
        corps_a = piste_a["data"][:idx_cut_a].copy()
        
        # 2. Construction de la séquence FX de transition
        audio_cue = piste_a["data"][max(0, idx_cut_a - int(beat_sec_a * 2 * sr)):idx_cut_a]
        
        if style_fx == "stutter_brake":
            # 2 beats de Stutter Roll + 2 beats de Vinyl Brake (1 mesure complète)
            duree_brake_sec = beat_sec_a * 2.0
            stutter = self.creer_stutter_roll(audio_cue, bpm_a, nb_beats=2.0)
            brake = self.creer_vinyl_brake(audio_cue, duree_sec=duree_brake_sec)
            silence_drop = np.zeros((int(0.04 * sr), 2), dtype=np.float32) # micro-silence avant l'impact
            transition_fx = np.vstack((stutter, brake, silence_drop))
            nom_technique = "STUTTER ROLL + TURNTABLE BRAKE"
            
        elif style_fx == "backspin":
            # 1 beat de montée + 2 beats de Backspin Rewind
            duree_spin = beat_sec_a * 2.0
            spin = self.creer_backspin(audio_cue, duree_sec=duree_spin)
            silence_drop = np.zeros((int(0.05 * sr), 2), dtype=np.float32)
            transition_fx = np.vstack((spin, silence_drop))
            nom_technique = "VINYL BACKSPIN REWIND"
            
        else: # "pure_brake"
            brake = self.creer_vinyl_brake(audio_cue, duree_sec=beat_sec_a * 2.0)
            silence_drop = np.zeros((int(0.04 * sr), 2), dtype=np.float32)
            transition_fx = np.vstack((brake, silence_drop))
            nom_technique = "PURE TURNTABLE MOTOR STOP"

        # 3. Piste B démarre immédiatement sur son gros drop / refrain
        idx_start_b = int(cue_in_b_sec * sr)
        corps_b = piste_b["data"][idx_start_b:].copy()
        
        # Mini-fondu d'entrée de 2ms sur B pour une attaque ultra propre sans craquement
        fade_in = int(0.002 * sr)
        if len(corps_b) > fade_in:
            corps_b[:fade_in] *= np.linspace(0.0, 1.0, fade_in)[:, None]
            
        # Assemblage final du mix
        mix_final = np.vstack((corps_a, transition_fx, corps_b))
        
        # Normalisation dynamique douce pour éviter toute saturation
        max_val = np.max(np.abs(mix_final))
        if max_val > 0.99:
            mix_final = mix_final * (0.95 / max_val)
            
        info = {
            "technique": f"ROUTINE DJ CLUB ({nom_technique})",
            "piste_a_intro": f"0:00 -> {int(cue_out_a_sec)}s ({piste_a['nom']})",
            "transition_fx": f"{len(transition_fx)/sr:.2f}s d'effet de platine en direct",
            "piste_b_drop": f"Impact direct à {int(cue_in_b_sec)}s sur le refrain ({piste_b['nom']})",
            "bpm_a": bpm_a,
            "bpm_b": bpm_b,
            "duree_totale_sec": round(len(mix_final)/sr, 1)
        }
        return mix_final, sr, info
