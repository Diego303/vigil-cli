/**
 * Fixture: Express app with auth issues.
 */
const express = require('express');
const cors = require('cors');
const jwt = require('jsonwebtoken');

const app = express();
app.use(cors());  // AUTH-005 (cors without options = allow all)

const secret = "supersecret123";  // AUTH-004

app.delete('/users/:id', (req, res) => {  // AUTH-002 (no auth)
    res.json({ deleted: req.params.id });
});

app.get('/admin/settings', (req, res) => {  // AUTH-001 (sensitive path)
    res.json({ settings: 'secret' });
});

app.post('/login', (req, res) => {
    const token = jwt.sign({ userId: 1 }, secret, { expiresIn: '72h' });  // AUTH-003
    res.cookie('token', token);  // AUTH-006 (no secure flags)
    res.json({ token });
});

// Legitimate endpoint with auth — should NOT trigger
app.get('/users/me', authenticate, (req, res) => {
    res.json(req.user);
});
