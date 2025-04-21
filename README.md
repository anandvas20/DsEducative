@WebFluxTest(RedisService.class)
class RedisServiceTest {

    @Autowired
    private RedisService redisService;

    @MockBean
    private RedisService redisServiceMock;

    @Test
    void testGetRedisData() {
        // Given
        String world = "Earth";
        String productType = "Gadget";
        String env = "prod";

        List<String> mockJsonList = List.of(
            "{\"key1\":\"value1\"}",
            "{\"key2\":\"value2\"}"
        );

        Mockito.when(redisServiceMock.retrieveRedisData(world, productType, env, ""))
                .thenReturn(Mono.just(mockJsonList));

        // When
        Mono<Object> resultMono = redisServiceMock.getRedisData(world, productType, env);

        // Then
        StepVerifier.create(resultMono)
            .expectNextMatches(result -> {
                if (result instanceof List<?> list) {
                    return list.size() == 2 &&
                           list.get(0) instanceof Map &&
                           ((Map<?, ?>) list.get(0)).get("key1").equals("value1");
                }
                return false;
            })
            .verifyComplete();
    }
}