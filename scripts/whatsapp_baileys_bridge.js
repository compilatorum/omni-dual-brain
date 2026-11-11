/**
 * Ponte Direta Node.js + @whiskeysockets/baileys (100% Real, Gratuita e Sem WhatsApp Business)
 * Suporta tanto Pareamento por Código de 8 Dígitos (Pairing Code para +5531984353632)
 * quanto QR Code Multi-Device, integrado ao Gateway Python (http://127.0.0.1:8765).
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  Browsers,
} = require("@whiskeysockets/baileys");
const QRCode = require("qrcode");
const qrcodeTerminal = require("qrcode-terminal");
const pino = require("pino");
const fs = require("fs");
const path = require("path");

const BASE_API_URL = process.env.OMNI_BASE_URL || "http://127.0.0.1:8765";
const WEBHOOK_SINGLE_URL = `${BASE_API_URL}/webhooks/whatsapp/single`;
const BRIDGE_STATE_URL = `${BASE_API_URL}/api/v1/whatsapp/bridge-state`;
const PAIRING_PHONE = (process.env.WHATSAPP_PAIRING_PHONE || "5531984353632").replace(/[^0-9]/g, "");

const REPO_QR_PNG = path.resolve(__dirname, "../docs/screenshots/real_whatsapp_qr.png");
const ARTIFACT_QR_PNG =
  "/home/sukata/.gemini/antigravity-cli/brain/541ed0e4-3b06-479a-9fcf-53906d49a401/real_whatsapp_qr.png";

const sentMessageIds = new Set();
let pairingCodeRequested = false;

async function pushBridgeState(updatePayload) {
  try {
    await fetch(BRIDGE_STATE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...updatePayload,
        updated_at: new Date().toISOString(),
      }),
    });
  } catch (_err) {
    // Ignora caso o servidor HTTP esteja reiniciando
  }
}

function extractPhoneE164(jid) {
  if (!jid) return "";
  const clean = jid.split("@")[0].split(":")[0].replace(/[^0-9]/g, "");
  return clean ? `+${clean}` : "";
}

async function startWhatsAppPersonalBridge() {
  const authDir = path.resolve(__dirname, "../.wa_auth_session");
  const { state, saveCreds } = await useMultiFileAuthState(authDir);
  const { version } = await fetchLatestBaileysVersion();

  console.log(`[OMNI-BRIDGE] Iniciando Baileys v${version.join(".")} para +${PAIRING_PHONE}...`);

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }),
    printQRInTerminal: false,
    browser: Browsers.ubuntu("Chrome"),
  });

  sock.ev.on("creds.update", saveCreds);

  // Registra antecipadamente +5531984353632 e +553184353632 como Admin no servidor Python
  await pushBridgeState({ connected_phone: "+5531984353632" });
  await pushBridgeState({ connected_phone: "+553184353632" });

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      // Assim que o canal Noise/QR abre, solicita o Pairing Code de 8 dígitos para +5531984353632
      if (!sock.authState.creds.registered && PAIRING_PHONE && !pairingCodeRequested) {
        pairingCodeRequested = true;
        try {
          const rawCode = await sock.requestPairingCode(PAIRING_PHONE);
          const formattedCode = rawCode?.match(/.{1,4}/g)?.join("-") || rawCode;
          console.log("\n========================================================");
          console.log(`🔑 [PAIRING CODE WHATSAPP PARA +${PAIRING_PHONE}]:  ${formattedCode}`);
          console.log("========================================================\n");
          await pushBridgeState({
            connection: "pairing_code_ready",
            pairing_code: formattedCode,
            target_phone: `+${PAIRING_PHONE}`,
          });
        } catch (pairErr) {
          console.error("Erro ao solicitar Pairing Code:", pairErr);
        }
      }

      try {
        fs.mkdirSync(path.dirname(REPO_QR_PNG), { recursive: true });
        await QRCode.toFile(REPO_QR_PNG, qr, {
          width: 420,
          margin: 2,
          color: { dark: "#0f172a", light: "#ffffff" },
        });
        if (fs.existsSync(path.dirname(ARTIFACT_QR_PNG))) {
          fs.copyFileSync(REPO_QR_PNG, ARTIFACT_QR_PNG);
        }
        const qrDataUrl = await QRCode.toDataURL(qr, { width: 320, margin: 2 });
        await pushBridgeState({
          qr_data_url: qrDataUrl,
        });
      } catch (_qrErr) {}
    }

    if (connection === "open") {
      const myPhone = extractPhoneE164(sock.user?.id);
      console.log(`✅ [OMNI DUAL-BRAIN] CONECTADO AO WHATSAPP REAL! Número Admin: ${myPhone}`);
      await pushBridgeState({
        connection: "connected",
        connected_phone: myPhone,
        qr_data_url: null,
      });

      if (sock.user?.id) {
        const selfJid = `${sock.user.id.split(":")[0].split("@")[0]}@s.whatsapp.net`;
        const welcome = await sock.sendMessage(selfJid, {
          text:
            "🧠 *[Omni Dual-Brain Conectado]*\n" +
            `Seu número (${myPhone}) foi autenticado na *Fronteira Interna (role = admin)*.\n\n` +
            "• Envie uma mensagem aqui mesmo (conversa com você mesmo) ou comece com *!omni* em qualquer chat.\n" +
            "• Exemplo 1 (KarmaHQ HITL): *Analise os commits da semana no GitHub e os casts com mais corações na Neynar e monte o JSON do KarmaHQ*\n" +
            "• Exemplo 2 (Archon): *Corrija isso no fluxo de agendamento*",
        });
        if (welcome?.key?.id) sentMessageIds.add(welcome.key.id);
      }
    } else if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const isRegistered = Boolean(sock.authState?.creds?.registered);
      console.log(`⚠️ [OMNI-BRIDGE] Conexão fechada (status=${statusCode}, registered=${isRegistered}).`);
      pairingCodeRequested = false;

      if (!isRegistered && (statusCode === DisconnectReason.loggedOut || statusCode === 401 || statusCode === 408)) {
        try {
          fs.rmSync(authDir, { recursive: true, force: true });
        } catch (_e) {}
      }
      setTimeout(() => startWhatsAppPersonalBridge(), 3000);
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    const myPhone = extractPhoneE164(sock.user?.id);

    for (const msg of messages) {
      if (!msg.message) continue;
      const msgId = msg.key.id || "";
      if (sentMessageIds.has(msgId)) continue;

      const remoteJid = msg.key.remoteJid || "";
      if (remoteJid.endsWith("@g.us") || remoteJid === "status@broadcast") continue;

      const senderPhone = msg.key.fromMe ? myPhone : extractPhoneE164(remoteJid);
      const rawText =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        "";

      if (!rawText) continue;
      if (rawText.startsWith("🧠 *[Omni Dual-Brain")) continue;

      const isSelfChat =
        extractPhoneE164(remoteJid) === myPhone ||
        remoteJid.includes("5531984353632") ||
        remoteJid.includes("553184353632");

      if (msg.key.fromMe && !isSelfChat && !rawText.trim().toLowerCase().startsWith("!omni")) {
        continue;
      }

      const cleanedText = rawText.replace(/^!omni\s*/i, "").trim();
      if (!cleanedText) continue;

      console.log(`📩 [WA REAL] De ${senderPhone}: "${cleanedText}"`);

      try {
        const res = await fetch(WEBHOOK_SINGLE_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message_id: msgId || String(Date.now()),
            user_id: senderPhone || "+5531984353632",
            channel: "whatsapp",
            text: cleanedText,
          }),
        });
        const data = await res.json();
        if (data.reply_text) {
          const formattedReply = `🧠 *[Omni Dual-Brain | role=${data.role}]*\n\n${data.reply_text}`;
          const sent = await sock.sendMessage(remoteJid, { text: formattedReply });
          if (sent?.key?.id) sentMessageIds.add(sent.key.id);
        }
      } catch (err) {
        console.error("Erro ao processar mensagem no Omni Dual-Brain:", err);
      }
    }
  });
}

startWhatsAppPersonalBridge();
