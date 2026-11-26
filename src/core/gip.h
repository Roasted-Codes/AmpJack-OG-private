/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * GIP, the Xbox One / Series controller protocol: framing, chunking, the
 * announce/identify/power handshake, security handshake and gamepad input.
 * Ported from xone (bus/protocol.c, auth/auth.c, driver/gamepad.c),
 * Copyright (C) 2021-2023 Severin von Wnuck-Lipinski.
 */
#pragma once

#include "dongle.h"
#include "sha256.h"

#define GIP_AUTH_RANDOM_LEN 32
#define GIP_AUTH_SECRET_LEN 48
#define GIP_AUTH2_PUBKEY_LEN 64

/* gamepad state in GIP's own units */
struct gip_gamepad_state {
	u16 buttons;  /* GIP_GP_BTN_* */
	bool guide;
	u16 trigger_left, trigger_right; /* 0..1023 */
	s16 stick_left_x, stick_left_y, stick_right_x, stick_right_y; /* up = positive */
};

enum gip_gamepad_button {
	GIP_GP_BTN_MENU = BIT(2),
	GIP_GP_BTN_VIEW = BIT(3),
	GIP_GP_BTN_A = BIT(4),
	GIP_GP_BTN_B = BIT(5),
	GIP_GP_BTN_X = BIT(6),
	GIP_GP_BTN_Y = BIT(7),
	GIP_GP_BTN_DPAD_U = BIT(8),
	GIP_GP_BTN_DPAD_D = BIT(9),
	GIP_GP_BTN_DPAD_L = BIT(10),
	GIP_GP_BTN_DPAD_R = BIT(11),
	GIP_GP_BTN_BUMPER_L = BIT(12),
	GIP_GP_BTN_BUMPER_R = BIT(13),
	GIP_GP_BTN_STICK_L = BIT(14),
	GIP_GP_BTN_STICK_R = BIT(15),
};

struct gip_client;

struct gip_ops {
	void (*ready)(struct gip_client *gc);   /* authenticated, input flows */
	void (*input)(struct gip_client *gc, const struct gip_gamepad_state *state);
	void (*gone)(struct gip_client *gc);    /* controller turned off */
	/* optional: a headset in the controller's jack is ready (present) or gone. When ready,
	 * gc->hs has the negotiated rates; earpiece audio goes out with gip_headset_send */
	void (*headset)(struct gip_client *gc, bool present);
	/* optional: microphone samples, s16 little-endian mono at gc->hs.rate_in */
	void (*audio_in)(struct gip_client *gc, const u8 *samples, int len);
};

struct gip_auth {
	struct sha256 transcript;
	u8 last_sent;
	bool done;
	u8 random_host[GIP_AUTH_RANDOM_LEN];
	u8 random_client[GIP_AUTH_RANDOM_LEN];
	u8 master_secret[GIP_AUTH_SECRET_LEN];
};

struct gip_chunk_buf {
	u8 command, options, sequence;
	u32 length;
	u8 *data;
};

/*
 * How a client's packets leave the host: the wireless adapter (one 802.11 client per
 * controller) or a USB cable (one interrupt OUT endpoint per controller).
 */
struct gip_transport {
	/* one complete GIP packet; 0 or a negative error */
	int (*send)(void *ctx, const u8 *data, int len);
	/* the session key from the security handshake; NULL = the link isn't encrypted */
	int (*set_key)(void *ctx, const u8 *key, int len);
	/* wired: input flows once the controller is powered on, without the security
	 * handshake (as Linux's xpad drives it); the handshake is skipped */
	bool no_auth;
	/* a USB cable: the controller may have announced itself before we listened, so a
	 * silent one is asked to identify itself, then started blind (gip_poll) */
	bool wired;
	/* optional, headset audio (wired: interface 1, isochronous). enable_audio selects
	 * the audio interface's streaming setting and starts the IN stream; send_audio sends
	 * `frames` GIP audio packets of frame_len bytes each, one per 1 ms USB frame */
	int (*enable_audio)(void *ctx, bool on);
	int (*send_audio)(void *ctx, const u8 *data, int frame_len, int frames);
};

/* the headset in the controller's jack (GIP client 1), as xone's driver/headset.c */
enum gip_hs_state {
	GIP_HS_NONE, GIP_HS_IDENTIFYING, GIP_HS_FORMAT, GIP_HS_STARTING, GIP_HS_READY,
};

/* The jack headset's own volume settings: the Audio Control Volume (Extended) message,
 * MS-GIPUSB 3.2.5.1.1 (control type 0x03, then these fields, then 2 reserved bytes). Each
 * field's bit 7 means "writable by the host" in the headset's reports; bits 6-0 are the value.
 * The headset mixes its own mic into the earpiece at GIP_VOL_SIDETONE % (its DSP: no USB
 * latency); its default is 0. */
enum {
	GIP_VOL_FLAGS,    /* GIP_VOL_F_* */
	GIP_VOL_SPEAKER,  /* 0..100 %, the earpiece */
	GIP_VOL_BALANCE,  /* 0 all game .. 100 all chat (two-stream headsets; 50 here) */
	GIP_VOL_MIC,      /* 0..100 %, the mic's gain in the headset */
	GIP_VOL_SIDETONE, /* 0..100 %, the mic in the earpiece (mic monitoring) */
	GIP_VOL_FIELDS,
	GIP_VOL_REPORT = GIP_VOL_FIELDS + 2 /* with the two reserved bytes */
};
#define GIP_VOL_WRITABLE 0x80
#define GIP_VOL_F_UP_MUTED 0x01   /* the capture (mic) stream is muted */
#define GIP_VOL_F_DOWN_MUTED 0x02 /* the render (earpiece) stream is muted */
#define GIP_VOL_F_HEADSET 0x04    /* a headset is detected (xone's "unmuted" 0x04) */

struct gip_headset {
	enum gip_hs_state state;
	u8 formats[32]; /* {in, out} pairs from the identify packet */
	u8 format_count;
	u8 fmt_in, fmt_out;
	u32 rate_in, rate_out;   /* Hz */
	u8 channels_in, channels_out;
	u32 buffer_out;          /* bytes per 8 ms block, earpiece */
	u32 fragment_out;        /* bytes per 1 ms packet */
	u64 next_power;
	u64 probe_until; /* gip_headset_probe: no identify answer by then = no headset */
	u64 resume_until; /* gip_headset_resume: no format answer by then = take it as is */
	u8 power_tries;
	bool got_volume, got_audio;
	u8 audio_seq;
	u32 packets_in, packets_out;
	/* the flow field (le16) of received audio packets: how many were below / equal to /
	 * above fragment_out, the smallest, the largest and the last (diagnostics) */
	u32 flow_below, flow_equal, flow_above, flow_min, flow_max, flow_last;
	/* Audio Control Volume (Extended), MS-GIPUSB 3.2.5.1.1, both ways, GIP_VOL_* order:
	 * the headset's last report (vol_rx_len bytes from the flags on, bit 7 of each field =
	 * writable by the host) and how many it sent; what we last sent and how many */
	u8 vol_rx[GIP_VOL_REPORT], vol_rx_len;
	u32 vol_reports;
	u8 vol_tx[GIP_VOL_FIELDS];
	u32 vol_sent;
};

struct gip_client {
	struct xa_client *xc; /* wireless only, else NULL */
	const struct gip_transport *tr;
	void *tr_ctx;
	int id;               /* for the log: the wireless client id or the wired port */
	const struct gip_ops *ops;
	void *user;
	bool ready;           /* ops->ready has been called: input is being reported */
	u64 started;          /* wired: when the client was created, for the start fallback */
	bool fallback;        /* wired: started without an announce (it may still come) */
	bool asked_identify;  /* wired: identify requested by the start fallback */

	u8 sequence;
	u16 vendor, product, version;
	bool identified, gamepad;

	struct gip_chunk_buf in;  /* chunked packet being received (client 0, the pad) */
	struct gip_chunk_buf out; /* chunked packet being sent */
	struct gip_chunk_buf hin, hout; /* the same for client 1, the jack headset */
	u8 cur;                   /* the GIP client being handled or sent to: 0 pad, 1 headset */
	struct gip_headset hs;
	bool hs_seen;         /* a headset announced itself in this session (client 1) */
	/* the last audio format the jack headset accepted (in this session, or handed over by
	 * the previous build): gip_headset_resume restarts it without an identify. Kept across
	 * hs_gone (the headset state is wiped, this isn't) */
	u8 hs_known_in, hs_known_out;

	struct gip_auth auth;
	struct gip_gamepad_state state;

	/* rumble: wanted vs. last sent (left, right, left trigger, right trigger) */
	u8 rumble[4], rumble_sent[4];
	u64 rumble_last;
};

/* a controller behind the wireless adapter */
struct gip_client *gip_client_new(struct xa_client *xc, const struct gip_ops *ops, void *user);
/* a controller on any other transport (a USB cable); id is only used in the log */
struct gip_client *gip_client_new_transport(const struct gip_transport *tr, void *ctx, int id,
					    const struct gip_ops *ops, void *user);
void gip_client_free(struct gip_client *gc);
void gip_rx(struct gip_client *gc, const u8 *data, int len);

/* motor strengths 0..100: main left/right, impulse triggers left/right */
void gip_set_rumble(struct gip_client *gc, u8 left, u8 right, u8 trigger_left,
		    u8 trigger_right);
/* send the current levels again at the next gip_poll, even unchanged (a stop the
 * controller's firmware may have dropped: it would otherwise run for minutes) */
void gip_rumble_resend(struct gip_client *gc);

/* timers (rumble pacing, headset start-up); call every few milliseconds */
void gip_poll(struct gip_client *gc);

/* earpiece audio: one 8 ms block, gc->hs.buffer_out bytes of s16 little-endian at
 * gc->hs.rate_out (NULL = silence). 0, or a negative error (no headset ready) */
int gip_headset_send(struct gip_client *gc, const u8 *block);
/* the same with only the first `packets` (1..GIP_AUDIO_BLOCK_PACKETS) packets of the block */
#define GIP_AUDIO_BLOCK_PACKETS 8
int gip_headset_send_n(struct gip_client *gc, const u8 *block, int packets);
/* the jack headset's own volume settings: v = the GIP_VOL_FIELDS fields (flags, speaker,
 * balance, mic, sidetone), sent as an Audio Control Volume message and kept in
 * gc->hs.vol_tx. The headset answers with a report of what it applied (gc->hs.vol_rx).
 * 0, or a negative error (no headset ready) */
int gip_headset_set_volume(struct gip_client *gc, const u8 *v);
/* forget the jack headset (audio off) and ask it to identify itself again, as if it had just
 * been plugged in: the transport sees enable_audio(false), then enable_audio(true) again once
 * it answers. -XA_ENODEV if no headset announced itself in this session. */
int gip_headset_reidentify(struct gip_client *gc);
/* restarts the jack headset's audio with a format it accepted before (fmt_in/fmt_out, or 0/0
 * for gc->hs_known_*), with no identify request: a headset that is already running ignores
 * one. The transport sees enable_audio(false) if it was on, then enable_audio(true); the
 * headset is put to sleep, offered the format and powered on, as after an identify. If it
 * doesn't answer the format within 1 s, the format is taken as accepted; audio packets
 * arriving meanwhile count as the answer. -XA_ENODEV if no format is known. */
int gip_headset_resume(struct gip_client *gc, u8 fmt_in, u8 fmt_out);

/* Hot reload (xw.xex): the controller was taken over from a previous instance of the host
 * driver, without a USB reset. It is switched on and won't announce itself again, so it is
 * asked to identify itself at once (instead of after the start fallback's wait); an
 * unanswered request still ends in the blind start. Wired transports only. */
void gip_adopt(struct gip_client *gc);
/* the same for the jack headset, which announced itself to the previous instance: asks
 * client 1 to identify itself. No answer within 2 s = no headset (a later announce is then
 * handled as usual). 0, or a negative error; does nothing if a headset is already known. */
int gip_headset_probe(struct gip_client *gc);
