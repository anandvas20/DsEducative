import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.StringRedisSerializer;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.zip.GZIPOutputStream;

import static org.assertj.core.api.Assertions.assertThat;

public class GzipStringRedisSerializerTest {

    private final String original = "Test string";

    @Test
    void testDeserialize_withGzipEnabled_andCompressedBytes() throws IOException {
        GzipStringRedisSerializer serializer = new GzipStringRedisSerializer(true);
        byte[] compressed = compress(original);
        String result = serializer.deserialize(compressed);
        assertThat(result).isEqualTo(original);
    }

    @Test
    void testDeserialize_withGzipDisabled_shouldReturnSameString() {
        GzipStringRedisSerializer serializer = new GzipStringRedisSerializer(false);
        byte[] plain = new StringRedisSerializer().serialize(original);
        String result = serializer.deserialize(plain);
        assertThat(result).isEqualTo(original);
    }

    @Test
    void testDeserialize_nullBytes_shouldReturnNull() {
        GzipStringRedisSerializer serializer = new GzipStringRedisSerializer(true);
        String result = serializer.deserialize(null);
        assertThat(result).isNull();
    }

    @Test
    void testDeserialize_emptyBytes_shouldReturnNull() {
        GzipStringRedisSerializer serializer = new GzipStringRedisSerializer(true);
        String result = serializer.deserialize(new byte[0]);
        assertThat(result).isNull();
    }

    @Test
    void testDeserialize_withInvalidGzip_shouldReturnNull() {
        GzipStringRedisSerializer serializer = new GzipStringRedisSerializer(true);
        // Pass non-GZIP bytes that start with GZIP magic number to force exception
        byte[] invalidGzip = new byte[]{0x1f, 0x8b, 0x00, 0x00};
        String result = serializer.deserialize(invalidGzip);
        assertThat(result).isNull();
    }

    // Utility method to compress a string using GZIP
    private byte[] compress(String str) throws IOException {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(baos)) {
            gzip.write(str.getBytes());
        }
        return baos.toByteArray();
    }
}