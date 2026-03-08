// AI-generated Express server with security issues
const express = require('express');
const cors = require('cors');
const jwt = require('jsonwebtoken');

const app = express();

// AUTH-005: CORS allow all
app.use(cors());

// AUTH-004: Hardcoded secret
const JWT_SECRET = "my-super-secret-key";

// AUTH-002: DELETE without auth middleware
app.delete('/api/users/:id', (req, res) => {
    res.json({ deleted: req.params.id });
});

// AUTH-003: JWT with excessive lifetime
app.post('/api/login', (req, res) => {
    const token = jwt.sign(
        { userId: req.body.userId },
        JWT_SECRET,
        { expiresIn: '7d' }
    );
    res.json({ token });
});

// AUTH-006: Cookie without security flags
app.post('/api/session', (req, res) => {
    res.cookie('session_id', 'abc123');
    res.json({ ok: true });
});

// SEC-004: Env with default
const DB_PASSWORD = process.env.DB_PASSWORD || "default-password-123";

app.listen(3000);
