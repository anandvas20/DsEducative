import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

public class PromotionServiceTest {

    @Test
    void testGetPromotionDetails_CatchBlockTriggered() {
        // Create a JsonNode that will cause failure
        JsonNode badNode = new ObjectMapper().createObjectNode().putPOJO("bad", new Object() {
            // This anonymous object might be too generic for treeToValue(Object.class)
            // depending on Jackson settings and could cause JsonProcessingException
        });

        Mono<JsonNode> badMono = Mono.just(badNode);

        Mono<Object> result = YourClass.getPromotionDetails(badMono);  // No method signature change

        StepVerifier.create(result)
            .expectError(RuntimeException.class)
            .verify();
    }
}