import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

class RedisUtilTest {

    public static class RedisDeviceDto {
        public String name;
        public boolean active;
        public int count;
        public double price;
        public long timestamp;
        public List<String> tags;
    }

    @Test
    void testPrivatePopulateRedisDto() throws Exception {
        String json = """
            {
              "name": "DeviceA",
              "active": true,
              "count": 5,
              "price": 199.99,
              "timestamp": 1650000000000,
              "tags": ["sensor", "wifi"]
            }
        """;

        ObjectMapper mapper = new ObjectMapper();
        JsonNode rootNode = mapper.readTree(json);
        Iterator<Map.Entry<String, JsonNode>> fields = rootNode.fields();

        RedisDeviceDto dto = new RedisDeviceDto();

        // Access private static method via reflection
        Method method = YourClassName.class.getDeclaredMethod("populateRedisDto", RedisDeviceDto.class, Iterator.class);
        method.setAccessible(true);
        method.invoke(null, dto, fields); // null because it's a static method

        // Assertions
        assertEquals("DeviceA", dto.name);
        assertTrue(dto.active);
        assertEquals(5, dto.count);
        assertEquals(199.99, dto.price);
        assertEquals(1650000000000L, dto.timestamp);
        assertEquals(List.of("sensor", "wifi"), dto.tags);
    }
}