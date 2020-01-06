package slidingwindow;

/**
 * Problem Statement # Given an array of positive numbers and a positive number
 * ‘k’, find the maximum sum of any contiguous subarray of size ‘k’.
 * 
 * EX1: Input: [2, 1, 5, 1, 3, 2], k=3 Output: 9 Explanation: Subarray with
 * maximum sum is [5, 1, 3].
 *
 * 
 */
public class MaximumSumSubArrayOfSizeK {

	public static void main(String[] args) {
		int result = findMaximumSubArayOfKElements1(new int[] { 2, 1, 5, 1, 3, 2 }, 3);
		System.out.println("Maximum of Sub Arrays of K elements " + result);
		int result1 = findMaximumSubArayOfKElements2(new int[] { 2, 1, 5, 1, 3, 2 }, 3);
		System.out.println("Maximum of Sub Arrays of K elements " + result1);

	}

	/**
	 * 
	 * O(N*K)
	 */
	public static int findMaximumSubArayOfKElements1(int arr[], int k) {
		int result = Integer.MIN_VALUE;
		for (int i = 0; i <= arr.length - k; i++) {
			int sum = 0;
			for (int j = i; j < i + k; j++) {
				sum += arr[j];
			}
			if (result < sum) {
				result = sum;
			}
		}

		return result;

	}

	/*
	 * O(N)
	 */
	public static int findMaximumSubArayOfKElements2(int arr[], int k) {
		int result = Integer.MIN_VALUE;
		int windowSum = 0;
		int windowStart = 0;
		for (int windowEnd = 0; windowEnd < arr.length; windowEnd++) {
			windowSum += arr[windowEnd];
			if (windowEnd >= k - 1) {
				if (result < windowSum)
					result = windowSum;

				windowSum -= arr[windowStart];
				windowStart++;
			}

		}
		return result;
	}

}
