# Twilio WhatsApp + OTP Integration — Step-by-Step Procedure

## 1. Create a Twilio Account

1. Go to https://www.twilio.com/try-twilio and sign up
2. Verify your email and phone number
3. From the console dashboard, note your:
   - **Account SID** (starts with `AC`)
   - **Auth Token**

## 2. Configure WhatsApp Sandbox (Development)

1. Go to **Messaging > Try it out > Send a WhatsApp message** in the Twilio console
2. Follow the instructions to join the sandbox:
   - Send `join <sandbox-keyword>` to the Twilio sandbox number (e.g. `+14155238886`)
   - Each tester's phone must join the sandbox before receiving messages
3. Note the sandbox number: `whatsapp:+14155238886`

For production, apply for a Twilio WhatsApp Business Profile instead.

## 3. Set Environment Variables

Add these to your `backend/.env` file:

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_real_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
OTP_TTL_SECONDS=300
OTP_RESEND_COOLDOWN_SECONDS=60
OTP_MAX_ATTEMPTS=5
OTP_CODE_LENGTH=6
ENABLE_DEV_OTP_LOGGING=True
```

## 4. Start Infrastructure

```bash
cd backend

# Start PostgreSQL + Redis + MinIO
docker-compose up db redis minio -d

# Run migrations
python manage.py migrate

# Seed test data (creates farmer with phone +263771234567)
python manage.py seed_data
```

## 5. Start Celery Worker (separate terminal)

```bash
cd backend
celery -A config.celery_app worker -l info -c 2
```

You will see OTP codes logged here in dev mode:
```
[DEV OTP DELIVERY] phone=+263771234567 code=483921  *** NON-PRODUCTION ONLY ***
```

## 6. Start Django Server (separate terminal)

```bash
cd backend
python manage.py runserver 0.0.0.0:8000
```

## 7. Expose Local Webhook (for inbound WhatsApp messages)

Use ngrok to expose your local server:

```bash
ngrok http 8000
```

Note the HTTPS URL, e.g. `https://abc123.ngrok.io`

## 8. Configure Twilio Webhook URL

1. Go to **Messaging > Settings > WhatsApp sandbox settings** in Twilio console
2. Set **WHEN A MESSAGE COMES IN** to:
   ```
   https://abc123.ngrok.io/api/v1/whatsapp/webhook/
   ```
3. Method: **POST**
4. Save

## 9. Test OTP Flow — Step by Step

### 9a. Request OTP

```bash
curl -X POST http://localhost:8000/api/v1/auth/request-otp/ \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+263771234567"}'
```

**Expected response:**
```json
{
  "detail": "OTP sent to your WhatsApp. Check your messages.",
  "expires_in": 300
}
```

**Expected terminal output (Celery worker):**
```
WARNING 2025-03-24 10:30:15 otp_service [DEV OTP] phone=+263771234567 code=483921 expires_in=300s  *** NON-PRODUCTION ONLY ***
WARNING 2025-03-24 10:30:16 tasks [DEV OTP DELIVERY] phone=+263771234567 code=483921  *** NON-PRODUCTION ONLY ***
```

### 9b. Verify OTP

Copy the code from the terminal log:

```bash
curl -X POST http://localhost:8000/api/v1/auth/verify-otp/ \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+263771234567", "code": "483921"}'
```

**Expected response:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user_id": "a1b2c3d4-...",
  "role": "SMALLHOLDER_FARMER"
}
```

### 9c. Use Token for Authenticated Request

```bash
curl -X GET http://localhost:8000/api/v1/auth/me/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
```

### 9d. Logout

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<refresh_token>"}'
```

**Expected response:**
```json
{
  "detail": "Successfully logged out."
}
```

### 9e. Confirm Token is Blacklisted

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<blacklisted_refresh_token>"}'
```

**Expected:** 401 Unauthorized

## 10. Test Inbound WhatsApp Messages

1. Send "help" from your WhatsApp to the Twilio sandbox number
2. Check ngrok terminal for the POST request hitting `/api/v1/whatsapp/webhook/`
3. Check Django logs for the inbound message processing
4. You should receive a reply with the help menu

### Other commands to test:
- Send "my settlements" — returns settlement data
- Send "trace lot LOT-MVR-2025-001" — returns trace events
- Send "hello" — returns greeting with help menu

## 11. Troubleshooting

| Problem | Solution |
|---------|----------|
| OTP not delivered | Check Celery worker is running and TWILIO credentials are set |
| "Invalid Twilio webhook signature" | Ensure ngrok URL matches exactly what's in Twilio console |
| WhatsApp message not received | Ensure phone has joined Twilio sandbox |
| OTP expired immediately | Check `OTP_TTL_SECONDS` in .env (should be 300+) |
| Rate limited | Wait for cooldown period (`OTP_RESEND_COOLDOWN_SECONDS`) |
| Dev OTP not in logs | Check `ENABLE_DEV_OTP_LOGGING=True` and `DJANGO_DEBUG=True` |

## 12. Postman Test Sequence

1. **POST** `/api/v1/auth/request-otp/` — Body: `{"phone_number": "+263771234567"}`
2. **Read OTP from Celery terminal**
3. **POST** `/api/v1/auth/verify-otp/` — Body: `{"phone_number": "+263771234567", "code": "XXXXXX"}`
4. **Copy `access` and `refresh` tokens from response**
5. **GET** `/api/v1/auth/me/` — Header: `Authorization: Bearer <access>`
6. **GET** `/api/v1/farms/` — Header: `Authorization: Bearer <access>`
7. **POST** `/api/v1/auth/logout/` — Body: `{"refresh": "<refresh>"}`, Header: `Authorization: Bearer <access>`
8. **POST** `/api/v1/auth/refresh/` — Body: `{"refresh": "<refresh>"}` — Should return 401

## 13. Flutter Integration Notes

### Request OTP
```dart
final response = await http.post(
  Uri.parse('$baseUrl/api/v1/auth/request-otp/'),
  headers: {'Content-Type': 'application/json'},
  body: jsonEncode({'phone_number': '+263771234567'}),
);
// Show "Check your WhatsApp" screen
```

### Verify OTP
```dart
final response = await http.post(
  Uri.parse('$baseUrl/api/v1/auth/verify-otp/'),
  headers: {'Content-Type': 'application/json'},
  body: jsonEncode({
    'phone_number': '+263771234567',
    'code': otpController.text,
  }),
);
final data = jsonDecode(response.body);
// Store data['access'] and data['refresh'] securely
// Navigate to dashboard based on data['role']
```

### Authenticated Requests
```dart
final response = await http.get(
  Uri.parse('$baseUrl/api/v1/auth/me/'),
  headers: {
    'Authorization': 'Bearer $accessToken',
    'Content-Type': 'application/json',
  },
);
```

### Logout
```dart
final response = await http.post(
  Uri.parse('$baseUrl/api/v1/auth/logout/'),
  headers: {
    'Authorization': 'Bearer $accessToken',
    'Content-Type': 'application/json',
  },
  body: jsonEncode({'refresh': refreshToken}),
);
// Clear stored tokens, navigate to login
```

### Token Refresh
```dart
final response = await http.post(
  Uri.parse('$baseUrl/api/v1/auth/refresh/'),
  headers: {'Content-Type': 'application/json'},
  body: jsonEncode({'refresh': refreshToken}),
);
// Update stored access token
```

## 14. Production Checklist

- [ ] Set `ENABLE_DEV_OTP_LOGGING=False`
- [ ] Set `DJANGO_DEBUG=False`
- [ ] Apply for Twilio WhatsApp Business Profile
- [ ] Replace sandbox number with your approved WhatsApp number
- [ ] Set up proper domain with SSL for webhook URL
- [ ] Configure rate limiting at Nginx level too
- [ ] Set strong `DJANGO_SECRET_KEY`
- [ ] Review `OTP_TTL_SECONDS` (recommended: 300)
- [ ] Review `OTP_MAX_ATTEMPTS` (recommended: 5)
- [ ] Verify all audit logs are being written
