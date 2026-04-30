/**
 * ============================================================
 * gramsetu-whatsapp-gateway — WhatsApp → AI Bridge
 * ============================================================
 * 
 * Architecture:
 *   WhatsApp User → Baileys WebSocket → Gateway → GramSetu API → Response → WhatsApp
 * 
 * Features:
 *   - Multi-device WhatsApp Web connection (Baileys)
 *   - Text messages → GramSetu AI agent
 *   - Voice notes → download → Sarvam STT → processing
 *   - Images/photos → forward to VLM for document reading
 *   - Progress updates → sent as WhatsApp messages
 *   - Form screenshots → sent back as images
 *   - OTP handling through WhatsApp
 *   - Session persistence per WhatsApp number
 *   - Auto-reconnect with exponential backoff
 *   - Queue-based message processing (no drops)
 */

const {
    makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    downloadMediaMessage,
    delay,
} = require('@whiskeysockets/baileys')
const qrcode = require('qrcode-terminal')
const pino = require('pino')
const http = require('http')

// ── CONFIG ─────────────────────────────────────────────────
const GRAMSETU_URL = process.env.GRAMSETU_URL || 'http://localhost:8000'
const GRAMSETU_CHAT  = `${GRAMSETU_URL}/api/whatsapp/message`
const GRAMSETU_VOICE = `${GRAMSETU_URL}/api/whatsapp/voice`
const GRAMSETU_IMAGE = `${GRAMSETU_URL}/api/whatsapp/image`
const GRAMSETU_PING  = `${GRAMSETU_URL}/api/health`
const GATEWAY_PORT   = parseInt(process.env.PORT || '3001')
const GRAMSETU_WHATSAPP_NUMBER = process.env.GRAMSETU_WHATSAPP_NUMBER || ''

const logger = pino({
    transport: { target: 'pino-pretty', options: { colorize: true } },
    level: process.env.LOG_LEVEL || 'info',
})

// ── STATS ──────────────────────────────────────────────────
const stats = {
    started: new Date().toISOString(),
    totalMessages: 0,
    uniqueUsers: new Set(),
    voiceNotes: 0,
    images: 0,
    formsFilled: 0,
}

// ── FIRST-TIME USER DETECTION ──────────────────────────────
const knownUsers = new Set()  // phone numbers that have messaged before
try {
    const fs = require('fs')
    if (fs.existsSync('auth_info/users.json')) {
        const data = JSON.parse(fs.readFileSync('auth_info/users.json', 'utf8'))
        data.forEach(u => knownUsers.add(u))
    }
} catch {}

function saveUsers() {
    try {
        const fs = require('fs')
        fs.writeFileSync('auth_info/users.json', JSON.stringify([...knownUsers]))
    } catch {}
}

// ── STATE ──────────────────────────────────────────────────
let sock = null
let reconnectAttempts = 0
const MAX_RECONNECT = 20
const messageQueue = []
let processingQueue = false

// ── MESSAGE QUEUE WORKER ───────────────────────────────────
async function processQueue() {
    if (processingQueue || messageQueue.length === 0) return
    processingQueue = true

    while (messageQueue.length > 0) {
        const { from, msg } = messageQueue.shift()
        try {
            await processMessage(from, msg)
        } catch (err) {
            logger.error({ err: err.message }, 'Queue processing error')
        }
        // Rate limit: 1 message per second to avoid WhatsApp blocking
        await delay(1000)
    }

    processingQueue = false
}

// ── MEDIA HANDLERS ─────────────────────────────────────────

async function handleVoiceNote(from, message) {
    const phone = from.split('@')[0]
    logger.info({ phone }, 'Voice note received')

    try {
        // Send "listening..." indicator
        await sendTyping(from)

        // Download audio
        const audioBuffer = await downloadMediaMessage(
            message,
            'buffer',
            {},
            { logger }
        )

        if (!audioBuffer) {
            await sendMessage(from, '⚠️ Could not process voice note. Please try again or type your message.')
            return
        }

        // Send to GramSetu for Sarvam STT processing
        const formData = new FormData()
        formData.append('audio', new Blob([audioBuffer], { type: 'audio/ogg' }), 'voice.ogg')
        formData.append('phone', phone)
        formData.append('language', 'hi')

        const res = await fetch(GRAMSETU_VOICE, { method: 'POST', body: formData })
        const data = await res.json()

        if (data.text) {
            // Forward transcribed text to the agent
            await forwardToAgent(from, phone, data.text)
        } else {
            await sendMessage(from, '🎙️ Sorry, I couldn\'t understand the voice note. Please type your message.')
        }
    } catch (err) {
        logger.error({ err: err.message }, 'Voice note processing failed')
        await sendMessage(from, '❌ Voice processing error. Please try again.')
    }
}

async function handleImage(from, message) {
    const phone = from.split('@')[0]
    logger.info({ phone }, 'Image received')

    try {
        await sendTyping(from)

        // Download image
        const imageBuffer = await downloadMediaMessage(
            message,
            'buffer',
            {},
            { logger }
        )

        if (!imageBuffer) return

        // Convert to base64
        const base64 = Buffer.from(imageBuffer).toString('base64')

        // Send to GramSetu for VLM analysis (document reading, form detection, etc.)
        const res = await fetch(GRAMSETU_IMAGE, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone,
                image: base64,
                caption: message.message?.imageMessage?.caption || '',
            }),
        })
        const data = await res.json()

        if (data.response) {
            await sendMessage(from, data.response)
        }
    } catch (err) {
        logger.error({ err: err.message }, 'Image processing failed')
        await sendMessage(from, '❌ Could not process the image. Please try again.')
    }
}

// ── CORE: FORWARD MESSAGE TO AGENT ─────────────────────────

async function forwardToAgent(from, phone, text) {
    try {
        const res = await fetch(GRAMSETU_CHAT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                user_id: phone,
                phone: phone,
                language: 'hi',
                source: 'whatsapp',
            }),
        })

        if (!res.ok) {
            logger.error({ status: res.status }, 'GramSetu API error')
            await sendMessage(from, '⚠️ Having trouble processing. Please try again.')
            return
        }

        const data = await res.json()

        if (data.response) {
            // Split long messages (WhatsApp has char limits)
            await sendLongMessage(from, data.response)

            // If there's a screenshot, send it as image
            if (data.screenshot_b64) {
                await sendImage(from, data.screenshot_b64, 'Form Screenshot')
            }

            // If receipt is ready, send receipt info
            if (data.receipt_ready) {
                await sendMessage(from,
                    `📄 *Receipt Ready!*\n` +
                    `🔢 Reference: ${data.reference_number}\n\n` +
                    `Your application has been submitted successfully.`
                )
            }
        }

        if (data.status === 'wait_otp') {
            await sendMessage(from,
                '🔐 *OTP has been sent to your registered mobile number.*\n\n' +
                'Please reply with the 6-digit code to complete your application.'
            )
        }
    } catch (err) {
        logger.error({ err: err.message }, 'Agent forwarding failed')
        await sendMessage(from, '❌ Service temporarily unavailable. Please try again.')
    }
}

// ── WHATSAPP SEND HELPERS ─────────────────────────────────

async function sendMessage(to, text) {
    try {
        await sock.sendMessage(to, { text })
    } catch (err) {
        logger.error({ err: err.message, to }, 'Send failed')
    }
}

async function sendLongMessage(to, text) {
    // WhatsApp recommends under 4096 chars per message
    const maxLen = 3500
    if (text.length <= maxLen) {
        return sendMessage(to, text)
    }

    // Split at paragraph boundaries
    const parts = text.split('\n\n')
    let current = ''
    for (const part of parts) {
        if ((current + '\n\n' + part).length > maxLen) {
            if (current) {
                await sendMessage(to, current)
                current = ''
            }
            // If a single section is too long, split by sentence
            if (part.length > maxLen) {
                const sentences = part.split(/(?<=[।.!?])\s+/)
                for (const s of sentences) {
                    if ((current + ' ' + s).length > maxLen) {
                        if (current) await sendMessage(to, current)
                        current = s
                    } else {
                        current += ' ' + s
                    }
                }
            } else {
                current = part
            }
        } else {
            current += '\n\n' + part
        }
    }
    if (current) await sendMessage(to, current)
}

async function sendImage(to, base64, caption) {
    try {
        await sock.sendMessage(to, {
            image: Buffer.from(base64, 'base64'),
            caption: caption || 'GramSetu Screenshot',
        })
    } catch (err) {
        logger.error({ err: err.message }, 'Image send failed')
    }
}

async function sendTyping(to) {
    try {
        await sock.presenceSubscribe(to)
        await sock.sendPresenceUpdate('composing', to)
    } catch {}
}

// ── MESSAGE PROCESSOR ──────────────────────────────────────

async function processMessage(from, msg) {
    const message = msg.message
    if (!message) return

    const phone = from.split('@')[0]
    const jid = from

    // ── TEXT MESSAGE ────────────────────────────────────
    if (message.conversation || message.extendedTextMessage?.text) {
        const text = message.conversation || message.extendedTextMessage.text
        logger.info({ phone, text: text.substring(0, 80) }, 'Text message')

        // Track stats
        stats.totalMessages++
        stats.uniqueUsers.add(phone)

        // ── FIRST-TIME USER WELCOME ────────────────────
        if (!knownUsers.has(phone)) {
            knownUsers.add(phone)
            saveUsers()
            logger.info({ phone }, '🆕 New user!')

            // Send a welcome message before forwarding to agent
            await sendMessage(jid,
                '🙏 *नमस्ते! मैं GramSetu हूँ — आपका AI सरकारी फ़ॉर्म सहायक.*\n\n' +
                'मैं आपके लिए ये कर सकता हूँ:\n' +
                '✅ राशन कार्ड, पैन कार्ड, पेंशन\n' +
                '✅ आयुष्मान भारत, PM-किसान, जन धन\n' +
                '✅ जाति प्रमाण पत्र, जन्म प्रमाण पत्र\n' +
                '✅ किसी भी सरकारी योजना की जानकारी\n\n' +
                '🗣️ *बोलकर भी बता सकते हैं — मैं आवाज़ समझता हूँ!*\n\n' +
                '👉 अभी बताइए — आपको क्या चाहिए?'
            )
        }

        await sendTyping(jid)
        await forwardToAgent(jid, phone, text)
    }

    // ── VOICE NOTE ──────────────────────────────────────
    else if (message.audioMessage || message.pttMessage) {
        // Mark as listened
        await sock.readMessages([msg.key])
        await handleVoiceNote(jid, message)
    }

    // ── IMAGE ───────────────────────────────────────────
    else if (message.imageMessage) {
        await sock.readMessages([msg.key])
        await handleImage(jid, message)
    }

    // ── BUTTON REPLY / LIST REPLY ───────────────────────
    else if (message.buttonsResponseMessage) {
        const text = message.buttonsResponseMessage.selectedButtonId || message.buttonsResponseMessage.selectedDisplayText
        if (text) {
            await sendTyping(jid)
            await forwardToAgent(jid, phone, text)
        }
    }
    else if (message.listResponseMessage) {
        const text = message.listResponseMessage.title
        if (text) {
            await sendTyping(jid)
            await forwardToAgent(jid, phone, text)
        }
    }

    // ── DOCUMENT / STICKER / LOCATION ───────────────────
    else if (message.documentMessage) {
        await sock.readMessages([msg.key])
        const caption = message.documentMessage.caption || ''
        await sendTyping(jid)
        await forwardToAgent(jid, phone, caption || '[Document received]')
    }
    else if (message.stickerMessage) {
        await sock.readMessages([msg.key])
        // Stickers can't be processed, ignore
    }
    else if (message.locationMessage) {
        const loc = message.locationMessage
        const text = `Location: ${loc.degreesLatitude}, ${loc.degreesLongitude}`
        await sendTyping(jid)
        await forwardToAgent(jid, phone, text)
    }

    // Mark as read
    await sock.readMessages([msg.key])
}

// ── CONNECTION ────────────────────────────────────────────

async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info')

    sock = makeWASocket({
        auth: state,
        printQRInTerminal: true,
        logger,
        defaultQueryTimeoutMs: 60000,
        markOnlineOnConnect: true,
        syncFullHistory: false,
        generateHighQualityLinkPreview: true,
    })

    // ── QR Code ───────────────────────────────────────────
    sock.ev.on('connection.update', ({ qr, connection, lastDisconnect }) => {
        if (qr) {
            qrcode.generate(qr, { small: true })
            logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            logger.info('  SCAN this QR code with WhatsApp on your phone')
            logger.info('  Settings → Linked Devices → Link a Device')
            logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        }

        if (connection === 'open') {
            reconnectAttempts = 0
            logger.info('✅ WhatsApp connected!')
            logger.info(`   Bridge: ${GRAMSETU_URL}`)

            // Ping GramSetu to verify it's reachable
            fetch(GRAMSETU_PING)
                .then(r => r.json())
                .then(d => logger.info(`   GramSetu: ${d.status || 'reachable'}`))
                .catch(() => logger.warn('   GramSetu: unreachable — check if server is running'))

            // Send startup notification
            const adminPhone = process.env.ADMIN_PHONE || process.env.WHATSAPP_ADMIN
            if (adminPhone) {
                sock.sendMessage(`${adminPhone}@s.whatsapp.net`, {
                    text: '🤖 *GramSetu WhatsApp Bot is ONLINE*\n\nReady to process forms and answer queries.\n\nसेवा उपलब्ध है — कोई भी फ़ॉर्म भेजें।'
                }).catch(() => {})
            }
        }

        if (connection === 'close') {
            const code = lastDisconnect?.error?.output?.statusCode
            const reason = lastDisconnect?.error?.message || 'Unknown'
            logger.warn({ code, reason }, 'WhatsApp disconnected')

            // Should reconnect?
            if (code !== DisconnectReason.loggedOut) {
                reconnectAttempts++
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 60000)
                logger.info(`Reconnecting in ${delay / 1000}s (attempt ${reconnectAttempts}/${MAX_RECONNECT})`)

                if (reconnectAttempts < MAX_RECONNECT) {
                    setTimeout(connectToWhatsApp, delay)
                } else {
                    logger.error('Max reconnect attempts exceeded. Exiting.')
                    process.exit(1)
                }
            } else {
                logger.error('Logged out. Delete auth_info/ and restart to re-register.')
                process.exit(1)
            }
        }
    })

    // ── Credential Updates ──────────────────────────────
    sock.ev.on('creds.update', saveCreds)

    // ── Message Handler ─────────────────────────────────
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type !== 'notify') return

        for (const msg of messages) {
            // Skip messages from self/status
            if (msg.key.fromMe) continue
            if (msg.key.remoteJid === 'status@broadcast') continue

            const from = msg.key.remoteJid

            // Queue the message for processing
            messageQueue.push({ from, msg })

            // Process queue (triggers worker if not already running)
            processQueue()
        }
    })

    // ── Group ignore ────────────────────────────────────
    sock.ev.on('groups.update', () => {})
    sock.ev.on('group-participants.update', () => {})

    return sock
}

// ── HEALTH SERVER (for Docker healthcheck + public status) ──
const healthServer = http.createServer((req, res) => {
    if (req.url === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({
            status: 'ok',
            connected: sock ? true : false,
            activeUsers: stats.uniqueUsers.size,
            totalMessages: stats.totalMessages,
            voiceNotes: stats.voiceNotes,
            images: stats.images,
            formsFilled: stats.formsFilled,
            started: stats.started,
            gramsetuUrl: GRAMSETU_URL,
            gramsetuNumber: GRAMSETU_WHATSAPP_NUMBER || 'configure GRAMSETU_WHATSAPP_NUMBER env var',
        }))
    } else if (req.url === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
        res.end(`<!DOCTYPE html><html lang="hi"><head><meta charset="UTF-8"><title>GramSetu WhatsApp</title>
<style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;background:#f5f5f5}
.card{background:#fff;padding:40px;border-radius:16px;text-align:center;box-shadow:0 2px 20px rgba(0,0,0,.08);max-width:420px}
h1{font-size:24px;margin:0 0 8px}a{display:inline-block;background:#25D366;color:#fff;padding:12px 28px;
border-radius:24px;text-decoration:none;font-weight:600;margin-top:16px}</style></head><body>
<div class="card"><h1>🤖 GramSetu</h1><p style="color:#666">AI Government Form Assistant on WhatsApp</p>
${GRAMSETU_WHATSAPP_NUMBER ? `<a href="https://wa.me/${GRAMSETU_WHATSAPP_NUMBER.replace(/\+/g,'')}?text=नमस्ते">📱 Chat on WhatsApp</a>` 
  : '<p style="color:#888">Set GRAMSETU_WHATSAPP_NUMBER env var for click-to-chat link</p>'}
<p style="font-size:12px;color:#aaa;margin-top:24px">👥 ${stats.uniqueUsers.size} users served · 💬 ${stats.totalMessages} messages</p></div></body></html>`)
    } else {
        res.writeHead(404); res.end('Not found')
    }
})

healthServer.listen(GATEWAY_PORT, () => {
    logger.info(`Health server on http://localhost:${GATEWAY_PORT}/health`)
})

// ── MAIN ───────────────────────────────────────────────────

async function main() {
    logger.info('🚀 GramSetu WhatsApp Gateway starting...')
    logger.info(`   Backend: ${GRAMSETU_URL}`)

    // Health check GramSetu before starting
    try {
        const res = await fetch(GRAMSETU_PING)
        const data = await res.json()
        logger.info(`   GramSetu API: ${res.status === 200 ? '✅ OK' : '⚠️ ' + res.status}`)
    } catch {
        logger.warn('   GramSetu API: ⚠️ Unreachable — will retry on messages')
    }

    await connectToWhatsApp()
}

main().catch(err => {
    logger.fatal(err, 'Fatal error')
    process.exit(1)
})

// ── Graceful shutdown ──────────────────────────────────────
process.on('SIGINT', async () => {
    logger.info('Shutting down...')
    if (sock) await sock.end()
    healthServer.close()
    process.exit(0)
})

process.on('SIGTERM', async () => {
    logger.info('Shutting down...')
    if (sock) await sock.end()
    healthServer.close()
    process.exit(0)
})
