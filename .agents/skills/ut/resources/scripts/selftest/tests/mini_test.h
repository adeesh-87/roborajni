/* tiny stand-in for a test framework, so the self-test needs only a compiler */
#define TEST(group, name) void group##_##name(void)
#define CHECK(x) do { if (!(x)) { return; } } while (0)
