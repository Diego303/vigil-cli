/**
 * Fixture: JavaScript tests with various quality issues.
 */

// TEST-001: Test without assertions (jest)
test('should create user', () => {
  const user = createUser('alice');
  console.log(user);
});

// TEST-001: Another empty test
it('should handle login', () => {
  const result = login('user', 'pass');
});

// TEST-002: Trivial assertion — toBeTruthy
test('user exists', () => {
  const user = getUser(1);
  expect(user).toBeTruthy();
});

// TEST-002: Trivial assertion — toBeDefined
test('response is defined', () => {
  const response = fetchData();
  expect(response).toBeDefined();
});

// TEST-004: Skipped test (jest)
test.skip('broken feature', () => {
  expect(1 + 1).toBe(2);
});

// TEST-004: Skipped with xit
xit('another broken test', () => {
  expect(true).toBe(true);
});

// TEST-005: API test without status code
test('should get users', async () => {
  const response = await fetch('/api/users');
  const data = await response.json();
  expect(data.length).toBeGreaterThan(0);
});

// TEST-006: Mock mirrors
test('should calculate price', () => {
  const mockCalc = jest.fn().mockReturnValue(42);
  const result = mockCalc();
  expect(result).toBe(42);
});

// LEGITIMATE: Proper test — should NOT trigger
test('should add numbers correctly', () => {
  const result = add(2, 3);
  expect(result).toBe(5);
  expect(result).toBeGreaterThan(0);
});

// LEGITIMATE: Test with toThrow — should NOT trigger TEST-001
test('should throw on invalid input', () => {
  expect(() => divide(1, 0)).toThrow();
});
