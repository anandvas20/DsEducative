package com.qurateretail.customer360.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.qurateretail.customer360.dto.RedisAccessoryDto;
import com.qurateretail.customer360.dto.RedisDeviceDto;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.core.ReactiveValueOperations;
import org.springframework.data.redis.core.ScanOptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

public class RedisServiceTest {

    private RedisService redisService;
    private ReactiveRedisTemplate<String, String> redisTemplate;
    private ReactiveValueOperations<String, String> valueOperations;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        redisTemplate = Mockito.mock(ReactiveRedisTemplate.class);
        valueOperations = Mockito.mock(ReactiveValueOperations.class);
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);

        redisService = new RedisService(redisTemplate);
        redisService.redisKeyPrefix = "customer:";
        redisService.init();
    }

    @Test
    void testGetAllKeysAndValues_success() throws Exception {
        String key = "customer:123";
        RedisDeviceDto dto = new RedisDeviceDto();
        dto.setDeviceId("123");
        dto.setAccessories(List.of(new RedisAccessoryDto()));
        String json = objectMapper.writeValueAsString(dto);

        when(redisTemplate.scan(any(ScanOptions.class))).thenReturn(Flux.just(key));
        when(valueOperations.get(key)).thenReturn(Mono.just(json));

        StepVerifier.create(redisService.getAllKeysAndValues())
                .expectNextMatches(result -> result.getDeviceId().equals("123"))
                .verifyComplete();
    }

    @Test
    void testGetAllAccessories_success() throws Exception {
        String key = "customer:456";
        RedisAccessoryDto accessory = new RedisAccessoryDto();
        RedisDeviceDto dto = new RedisDeviceDto();
        dto.setDeviceId("456");
        dto.setAccessories(List.of(accessory));
        String json = objectMapper.writeValueAsString(dto);

        when(redisTemplate.scan(any(ScanOptions.class))).thenReturn(Flux.just(key));
        when(valueOperations.get(key)).thenReturn(Mono.just(json));

        StepVerifier.create(redisService.getAllAccessories("456"))
                .expectNextMatches(list -> list.size() == 1)
                .verifyComplete();
    }

    @Test
    void testGetAllAccessories_deviceIdMissing() {
        StepVerifier.create(redisService.getAllAccessories(""))
                .expectError(IllegalArgumentException.class)
                .verify();
    }

    @Test
    void testGetAllAccessories_notFound() throws Exception {
        when(redisTemplate.scan(any(ScanOptions.class))).thenReturn(Flux.empty());

        StepVerifier.create(redisService.getAllAccessories("999"))
                .expectErrorMatches(e -> e instanceof RuntimeException &&
                        e.getMessage().contains("No data found for deviceId"))
                .verify();
    }
}