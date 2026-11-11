/**
 * Ponte Direta Node.js + @whiskeysockets/baileys (100% Real, Gratuita e Sem WhatsApp Business)
 * Conecta um número pessoal comum do WhatsApp (via QR Code real ou Pairing Code)
 * diretamente ao Gateway Python do Omni Dual-Brain (http://127.0.0.1:8765).
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");
const QRCode = require("qrcode");
const qrcodeTerminal = require("qrcode-terminal");
const pino = require("pino");
const fs = require("fs");
const path = require("path");

const BASE_API_URL = process.env.OMNI_BASE_URL || "http://127.0.0.1:8765";
const WEBHOOK_SINGLE_URL = `${BASE_API_URL}/webhooks/whatsapp/single`;
const BRIDGE_STATE_URL = `${BASE_API_URL}/api/v1/whatsapp/bridge-state`;

const REPO_QR_PNG = path.resolve(__dirname, "../docs/screenshots/real_whatsapp_qr.png");
const ARTIFACT_QR_PNG =
  "/home/sukata/.gemini/antigravity-cli/brain/541ed0e4-3b06-479a-9fcf-53906d49a401/real_whatsapp_qr.png";

const sentMessageIds = new Set();

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
    // Servidor Python pode ainda estar subindo
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

  console.log(`[OMNI-BRIDGE] Iniciando Baileys v${version.join(".")} no protocolo WhatsApp Multi-Device...`);

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }),
    printQRInTerminal: false,
    browser: ["Omni Dual-Brain", "Chrome", "1.0.0"],
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\n📲 [OMNI DUAL-BRAIN] QR CODE REAL GERADO! Escaneie no seu WhatsApp pessoal (Aparelhos Conectados):");
      qrcodeTerminal.generate(qr, { small: true });

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
          connection: "qr_ready",
          qr_data_url: qrDataUrl,
          qr_raw: qr,
        });
        console.log(`✅ [OMNI-BRIDGE] Imagem PNG do QR Code salva em: ${REPO_QR_PNG}`);
      } catch (qrErr) {
        console.error("Erro ao salvar imagem do QR Code:", qrErr);
      }
    }

    if (connection === "open") {
      const myPhone = extractPhoneE164(sock.user?.id);
      console.log(`✅ [OMNI DUAL-BRAIN] CONECTADO AO WHATSAPP REAL! Número Admin: ${myPhone}`);
      await pushBridgeState({
        connection: "connected",
        connected_phone: myPhone,
        qr_data_url: null,
      });

      // Envia mensagem de boas-vindas para o próprio chat ("Mensagem para você mesmo")
      if (sock.user?.id) {
        const selfJid = `${ sock.user.id.split(":")[0].split("@")[0] }@s.whatsapp.net`;
        const welcome = await sock.sendMessage(selfJid, {
          text:
            "🧠 *[Omni Dual-Brain Conectado]*\n" +
            `Seu número (${myPhone}) foi autenticado na *Fronteira Interna (role = admin)*.\n\n` +
            "• Envie *!omni status* ou pergunte sobre commits do GitHub / casts da Neynar / KarmaHQ neste chat.\n" +
            "• Qualquer outro número que enviar mensagem cairá automaticamente na *Fronteira Externa (role = public)*.",
        });
        if (welcome?.key?.id) sentMessageIds.add(welcome.key.id);
      }
    } else if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      console.log(`⚠️ [OMNI-BRIDGE] Conexão fechada (status=${statusCode}). Reconectar=${shouldReconnect}`);
      await pushBridgeState({ connection: "disconnected", last_status_code: statusCode });
      if (shouldReconnect) {
        setTimeout(() => startWhatsAppPersonalBridge(), 2500);
      }
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
      // Evita loop infinito ignorando as próprias respostas geradas pelo bot
      if (rawText.startsWith("🧠 *[Omni Dual-Brain")) continue;

      // Se a mensagem foi enviada pelo próprio dono para outro chat, só processa se começar com !omni
      const isSelfChat = extractPhoneE164(remoteJid) === myPhone;
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
            user_id: senderPhone,
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
