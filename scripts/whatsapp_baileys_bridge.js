/**
 * Ponte Direta Node.js + @whiskeysockets/baileys (100% Gratuita e Sem Docker)
 * Conecta um número pessoal comum do WhatsApp (via QR Code no terminal)
 * diretamente ao Gateway Python do Omni Dual-Brain (http://127.0.0.1:8765).
 *
 * Como usar sem Docker:
 *   npm install @whiskeysockets/baileys qrcode-terminal pino
 *   node scripts/whatsapp_baileys_bridge.js
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require("@whiskeysockets/baileys");
const qrcode = require("qrcode-terminal");
const pino = require("pino");

const OMNI_GATEWAY_URL = process.env.OMNI_GATEWAY_URL || "http://127.0.0.1:8765/webhooks/whatsapp/single";

async function startWhatsAppPersonalBridge() {
  const { state, saveCreds } = await useMultiFileAuthState("./.wa_auth_session");

  const sock = makeWASocket({
    auth: state,
    logger: pino({ level: "silent" }),
    printQRInTerminal: false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      console.log("\n📲 [OMNI DUAL-BRAIN] Escaneie o QR Code abaixo no seu WhatsApp pessoal (Aparelhos Conectados):");
      qrcode.generate(qr, { small: true });
    }
    if (connection === "open") {
      console.log("✅ [OMNI DUAL-BRAIN] Conectado ao WhatsApp Pessoal via protocolo Multi-Device (Zero Custo)!");
    } else if (connection === "close") {
      const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      if (shouldReconnect) startWhatsAppPersonalBridge();
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      if (!msg.message || msg.key.fromMe) continue;
      const remoteJid = msg.key.remoteJid || "";
      const phoneE164 = "+" + remoteJid.replace(/@.*$/, "");
      const text =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        "";

      if (!text) continue;

      try {
        const res = await fetch(OMNI_GATEWAY_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message_id: msg.key.id || String(Date.now()),
            user_id: phoneE164,
            channel: "whatsapp",
            text,
          }),
        });
        const data = await res.json();
        if (data.reply_text) {
          await sock.sendMessage(remoteJid, { text: data.reply_text });
        }
      } catch (err) {
        console.error("Erro ao encaminhar mensagem para o Omni Dual-Brain:", err);
      }
    }
  });
}

startWhatsAppPersonalBridge();
