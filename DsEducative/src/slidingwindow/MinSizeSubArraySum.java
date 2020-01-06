package slidingwindow;

/**
 * Problem Statement # Given an array of positive numbers and a positive number
 * ‘S’, find the length of the smallest contiguous subarray whose sum is greater
 * than or equal to ‘S’. Return 0, if no such subarray exists.
 * 
 * Example 1:
 * 
 * Input: [2, 1, 5, 2, 3, 2], S=7 Output: 2 Explanation: The smallest subarray
 * with a sum great than or equal to '7' is [5, 2].
 * 
 * @author ANANDG
 *
 */
public class MinSizeSubArraySum {

	public static void main(String[] args) {
		int result = findMinSubArray(new int[] { 2, 1, 5, 2, 3, 2 }, 7);
		System.out.println("Minimum sub array length " + result);

	}

	public static int findMinSubArray(int arr[], int sum) {
		int windowStart = 0;
		int windowSum = 0;
		int minimumLength = Integer.MAX_VALUE;
		for (int windowEnd = 0; windowEnd < arr.length; windowEnd++) {
			windowSum += arr[windowEnd];
			while (windowSum >= sum) {
				minimumLength = Math.min(minimumLength, windowEnd - windowStart + 1);
				windowSum -= arr[windowStart];
				windowStart++;
			}

		}

		return minimumLength;
	}

}
