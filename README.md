@ExtendWith(MockitoExtension.class)
class TokenServiceTest {

    @InjectMocks
    private TokenService tokenService; // The class containing getTokenHttpService()

    @Mock
    private EpcProperties epcProperties;

    @Mock
    private HttpService tokenGenerator;

    @MockStatic(JsonToObjectConverter.class)
    private MockedStatic<JsonToObjectConverter> jsonConverterMock;

    private TokenModel tokenModel;

    @BeforeEach
    void setup() {
        tokenModel = new TokenModel();
        tokenModel.setRoles(List.of("ROLE_USER"));
        tokenModel.setSub("user@example.com");

        jsonConverterMock = Mockito.mockStatic(JsonToObjectConverter.class);
        jsonConverterMock.when(() ->
            JsonToObjectConverter.jsonToObject("token.json", TokenModel.class)
        ).thenReturn(tokenModel);
    }

    @AfterEach
    void tearDown() {
        jsonConverterMock.close();
    }

    @Test
    void testSuccessfulFlowWithAuth() {
        // Setup mocks
        EpcProperties.Token token = mock(EpcProperties.Token.class);
        when(token.getUserRoles()).thenReturn(List.of("ROLE_USER"));
        when(token.getSub()).thenReturn("user@example.com");
        when(epcProperties.getToken()).thenReturn(token);
        when(epcProperties.getUsername()).thenReturn("user");
        when(epcProperties.getPassword()).thenReturn("pass");

        String tokenJson = "{\"access_token\":\"abc\"}";
        when(tokenGenerator.postRequest(any(), any(), any())).thenReturn(Mono.just(tokenJson));

        // Run and verify
        StepVerifier.create(tokenService.getTokenHttpService())
            .expectNextMatches(token -> token.getAccessToken().equals("abc"))
            .verifyComplete();
    }

    @Test
    void testSuccessfulFlowWithoutAuth() {
        // Same as above but epcProperties.getUsername() and getPassword() return null
    }

    @Test
    void