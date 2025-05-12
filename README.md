import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpHeaders;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class TokenServiceTest {

    @InjectMocks
    private TokenService tokenService; // The class containing getTokenHttpService()

    @Mock
    private EpcProperties epcProperties;

    @Mock
    private HttpService tokenGenerator;

    @Mock
    private ObjectMapper mapper;

    private static MockedStatic<JsonToObjectConverter> jsonConverterMock;

    private TokenModel tokenModel;
    private EpcProperties.Token tokenConfig;

    @BeforeEach
    void setUp() {
        tokenModel = new TokenModel();
        tokenModel.setRoles(List.of("ROLE_USER"));
        tokenModel.setSub("user@example.com");

        tokenConfig = mock(EpcProperties.Token.class);
        when(tokenConfig.getUserRoles()).thenReturn(List.of("ROLE_USER"));
        when(tokenConfig.getSub()).thenReturn("user@example.com");
        when(epcProperties.getToken()).thenReturn(tokenConfig);

        jsonConverterMock = mockStatic(JsonToObjectConverter.class);
        jsonConverterMock.when(() ->
            JsonToObjectConverter.jsonToObject("token.json", TokenModel.class)
        ).thenReturn(tokenModel);
    }

    @AfterEach
    void tearDown() {
        jsonConverterMock.close();
    }

    @Test
    void testSuccessfulFlowWithUsernamePassword() throws Exception {
        when(epcProperties.getUsername()).thenReturn("user");
        when(epcProperties.getPassword()).thenReturn("pass");

        String jsonRequest = "{\"sub\":\"user@example.com\"}";
        when(mapper.writeValueAsString(any())).thenReturn(jsonRequest);

        String jsonResponse = "{\"accessToken\":\"abc123\"}";
        when(tokenGenerator.postRequest(anyString(), anyMap(), anyString()))
                .thenReturn(Mono.just(jsonResponse));

        Token expectedToken = new Token();
        expectedToken.setAccessToken("abc123");
        when(mapper.readValue(jsonResponse, Token.class)).thenReturn(expectedToken);

        StepVerifier.create(tokenService.getTokenHttpService())
            .expectNextMatches(token -> "abc123".equals(token.getAccessToken()))
            .verifyComplete();
    }

    @Test
    void testSuccessfulFlowWithoutUsernamePassword() throws Exception {
        when(epcProperties.getUsername()).thenReturn(null);
        when(epcProperties.getPassword()).thenReturn(null);

        when(mapper.writeValueAsString(any())).thenReturn("{\"mock\":\"json\"}");

        String jsonResponse = "{\"accessToken\":\"xyz789\"}";
        when(tokenGenerator.postRequest(anyString(), anyMap(), anyString()))
                .thenReturn(Mono.just(jsonResponse));

        Token token = new Token();
        token.setAccessToken("xyz789");
        when(mapper.readValue(jsonResponse, Token.class)).thenReturn(token);

        StepVerifier.create(tokenService.getTokenHttpService())
            .expectNextMatches(t -> "xyz789".equals(t.getAccessToken()))
            .verifyComplete();
    }

    @Test
    void testJsonSerializationFailure() throws Exception {
        when(mapper.writeValueAsString(any()))
                .thenThrow(new JsonProcessingException("Serialization Error") {});

        Assertions.assertThrows(RuntimeException.class,
            () -> tokenService.getTokenHttpService().block());
    }

    @Test
    void testJsonDeserializationFailure() throws Exception {
        when(epcProperties.getUsername()).thenReturn("user");
        when(epcProperties.getPassword()).thenReturn("pass");

        when(mapper.writeValueAsString(any())).thenReturn("{\"mock\":\"json\"}");
        when(tokenGenerator.postRequest(anyString(), anyMap(), anyString()))
                .thenReturn(Mono.just("{invalid-json"));

        when(mapper.readValue(anyString(), eq(Token.class)))
                .thenThrow(new JsonProcessingException("Deserialization Error") {});

        Assertions.assertThrows(RuntimeException.class,
            () -> tokenService.getTokenHttpService().block());
    }
}