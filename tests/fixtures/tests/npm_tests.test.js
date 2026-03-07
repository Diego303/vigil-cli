/**
 * Fixture: npm/jest project test file with mixed quality issues.
 */

const { createUser, deleteUser, getUser } = require('./userService');

// Clean test
test('creates a user with valid data', () => {
  const user = createUser({ name: 'Alice', email: 'alice@test.com' });
  expect(user.id).toBeDefined();
  expect(user.name).toBe('Alice');
  expect(user.email).toBe('alice@test.com');
});

// TEST-001: No assertions
test('deletes a user', () => {
  deleteUser(123);
});

// TEST-002: Trivial — only toBeDefined
test('user is defined', () => {
  const user = getUser(1);
  expect(user).toBeDefined();
});

// TEST-006: Mock mirror
test('get user returns mocked data', () => {
  const mockGet = jest.fn().mockReturnValue('alice');
  const result = mockGet();
  expect(result).toBe('alice');
});

// TEST-003: Catch all in JS
test('handles crash gracefully', () => {
  try {
    createUser(null);
  } catch(err) {
    console.log('caught');
  }
});

// Clean: proper API test with status
test('API health check', async () => {
  const res = await fetch('/api/health');
  expect(res.status).toBe(200);
  const body = await res.json();
  expect(body.ok).toBe(true);
});
