import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

public class DataFlowServicePrivateMethodTest {

    private DataFlowService service;
    private DataFlow mockDataFlow;

    @BeforeEach
    void setup() {
        service = new DataFlowService();
        mockDataFlow = mock(DataFlow.class);
        service.setDataFlow(mockDataFlow);
    }

    @Test
    void testPrivateGetEntityDetailsViaReflection() throws Exception {
        List<EntityRecord> data = Arrays.asList(
            new EntityRecord("Field1", "Sys1", "Val1"),
            new EntityRecord("Field1", "Sys2", "Val2")
        );
        when(mockDataFlow.getSystemsInOrder()).thenReturn(Arrays.asList("Sys1", "Sys2"));

        Method method = DataFlowService.class.getDeclaredMethod("getEntityDetails", List.class);
        method.setAccessible(true); // access private method

        EntityDetails result = (EntityDetails) method.invoke(service, data);

        assertNotNull(result);
        assertEquals(1, result.getEntityRowDetails().size());

        EntityRowDetails row = result.getEntityRowDetails().get(0);
        assertEquals("Field1", row.getField());
        assertEquals("Val1", row.getDetails().get("Sys1"));
        assertEquals("Val2", row.getDetails().get("Sys2"));
        assertFalse(row.isMatch());
    }
}