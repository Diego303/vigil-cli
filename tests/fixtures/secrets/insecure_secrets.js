/**
 * Fixture: JavaScript file with secret issues.
 */

// SEC-001: Placeholder
const apiKey = "your-api-key-here";
const secretKey = "TODO_replace_this";

// SEC-002: Low-entropy secret
const password = "admin123";

// SEC-003: Connection string
const dbUrl = "mongodb://admin:mongopass123@mongo.example.com:27017/myapp";

// SEC-004: Env with default
const jwtSecret = process.env.JWT_SECRET || "devsecret123";
const dbPassword = process.env.DB_PASSWORD || "localpassword";

// This should NOT trigger — proper env var usage
const safeKey = process.env.API_KEY;
