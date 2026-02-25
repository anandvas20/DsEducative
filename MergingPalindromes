import java.util.Objects;

public final class MergingPalindromes {

    private static final int ALPHABET_SIZE = 26;

    private MergingPalindromes() {
        // Prevent instantiation (utility class)
    }

    public static String mergePalindromes(String s1, String s2) {

        validateInput(s1, s2);

        int[] freq = buildFrequency(s1, s2);

        if (!canFormPalindrome(freq)) {
            return "Palindrome not possible";
        }

        return buildLexicographicallySmallestPalindrome(freq);
    }

    private static void validateInput(String s1, String s2) {
        Objects.requireNonNull(s1, "First string cannot be null");
        Objects.requireNonNull(s2, "Second string cannot be null");

        if (!s1.matches("[a-z]*") || !s2.matches("[a-z]*")) {
            throw new IllegalArgumentException("Only lowercase a-z allowed");
        }
    }

    private static int[] buildFrequency(String s1, String s2) {
        int[] freq = new int[ALPHABET_SIZE];

        for (char c : s1.toCharArray()) {
            freq[c - 'a']++;
        }

        for (char c : s2.toCharArray()) {
            freq[c - 'a']++;
        }

        return freq;
    }

    private static boolean canFormPalindrome(int[] freq) {
        int oddCount = 0;

        for (int count : freq) {
            if (count % 2 != 0) {
                oddCount++;
            }
        }

        return oddCount <= 1;
    }

    private static String buildLexicographicallySmallestPalindrome(int[] freq) {

        StringBuilder leftHalf = new StringBuilder();
        String middle = "";

        for (int i = 0; i < ALPHABET_SIZE; i++) {

            int pairs = freq[i] / 2;

            if (pairs > 0) {
                leftHalf.append(
                        String.valueOf((char) (i + 'a')).repeat(pairs)
                );
            }

            if (freq[i] % 2 != 0) {
                middle = String.valueOf((char) (i + 'a'));
            }
        }

        String rightHalf = leftHalf.reverse().toString();

        return leftHalf.reverse().toString() + middle + rightHalf;
    }

    public static void main(String[] args) {
        System.out.println(mergePalindromes("aabbcc", "ddeefq"));
        System.out.println(mergePalindromes("adaab", "cca"));
    }
}
