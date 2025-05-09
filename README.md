import org.junit.jupiter.api.Test;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class RedisServiceTest {

    @Test
    void testGetRedisAccessoryMappedJson_privateMethod() throws Exception {
        // Setup
        RedisService service = new RedisService();

        RedisAccessoryDto dto = new RedisAccessoryDto();
        // You may need to set values in dto based on your actual CommonUtil.getPropertiesMap logic

        // Mock static method CommonUtil.getPropertiesMap(dto)
        Map<String, String> dtoProps = new HashMap<>();
        dtoProps.put("productId", "123");
        dtoProps.put("type", "accessory");

        try (MockedStatic<CommonUtil> mocked = Mockito.mockStatic(CommonUtil.class)) {
            mocked.when(() -> CommonUtil.getPropertiesMap(dto)).thenReturn(dtoProps);

            // Inject mock runTimeMapInitializer
            RunTimeMapInitializer initializer = Mockito.mock(RunTimeMapInitializer.class);
            Map<String, String> map = new HashMap<>();
            map.put("id", "productId");
            map.put("category", "type");
            Mockito.when(initializer.getCacheMap("electronics")).thenReturn(map);

            // Use reflection to set the mock into the private field if needed
            Field field = RedisService.class.getDeclaredField("runTimeMapInitializer");
            field.setAccessible(true);
            field.set(service, initializer);

            // Reflectively invoke private method
            Method method = RedisService.class.getDeclaredMethod("getRedisAccessoryMappedJson", RedisAccessoryDto.class, String.class);
            method.setAccessible(true);
            @SuppressWarnings("unchecked")
            Map<String, String> result = (Map<String, String>) method.invoke(service, dto, "electronics");

            // Assertions
            assertEquals("123", result.get("id"));
            assertEquals("accessory", result.get("category"));
        }
    }
}