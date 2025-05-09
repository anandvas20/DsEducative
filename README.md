import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

public class RedisAccessoryMapperTest {

    @Test
    public void testMapToRedisAccessoryDto_validJson_shouldReturnDto() throws Exception {
        Map<String, String> concatenatedMap = new HashMap<>();

        // Sample JSON structures
        String dataJson = "{ \"sku\": \"12345\", \"name\": \"Test Product\" }";
        String responseJson = "{ " +
                "\"PRICE\": { \"value\": \"19.99\" }, " +
                "\"IMAGE_URL_MAP\": { \"main\": \"http://image.url/main.jpg\" }, " +
                "\"category\": \"accessory\" }";

        concatenatedMap.put("DATA", dataJson);
        concatenatedMap.put("RESPONSE", responseJson);

        RedisAccessoryDto result = RedisAccessoryMapper.mapToRedisAccessoryDto(concatenatedMap);

        assertNotNull(result);
        assertEquals("http://image.url/main.jpg", result.getImageUrlMap());
        // Add more assertions depending on how populate methods work
    }

    @Test
    public void testMapToRedisAccessoryDto_nullDataOrResponse_shouldReturnEmptyDto() throws Exception {
        Map<String, String> concatenatedMap = new HashMap<>();
        concatenatedMap.put("DATA", null);
        concatenatedMap.put("RESPONSE", null);

        RedisAccessoryDto result = RedisAccessoryMapper.mapToRedisAccessoryDto(concatenatedMap);

        assertNotNull(result);
        assertNull(result.getImageUrlMap()); // assuming default is null
    }
}