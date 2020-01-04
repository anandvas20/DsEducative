package slidingwindow;

import java.util.Arrays;

public class SubArrayAvgOfK {

	public static void main(String[] args) {
		double result[] = findAverages1(new int[] { 1, 3, 2, 6, -1, 4, 1, 8, 2 }, 5);
		System.out.println("The averges of sub arrays k elements  " + Arrays.toString(result));

		double result2[] = findAverages2(new int[] { 1, 3, 2, 6, -1, 4, 1, 8, 2 }, 5);
		System.out.println("The averges of sub arrays k elements  " + Arrays.toString(result2));

	}

	/*
	 * Approach 2 O(N)
	 */
	public static double[] findAverages2(int arr[], int k) {
		double result[] = new double[arr.length - k + 1];
		double windowSum = 0;
		int windowStart = 0;
		for (int windowEnd = 0; windowEnd < arr.length; windowEnd++) {
			windowSum += arr[windowEnd];
			if (windowEnd >= k - 1) {
				result[windowStart] = windowSum / k;
				windowSum -= arr[windowStart];
				windowStart++;
			}

		}

		return result;

	}

	/*
	 * Approach 1 complexity O(n*k)
	 */

	public static double[] findAverages1(int arr[], int k) {
		double result[] = new double[arr.length - k + 1];
		for (int i = 0; i <= arr.length - k; i++) {
			double sum = 0;
			for (int j = i; j < i + k; j++) {
				sum += arr[j];
			}
			result[i] = sum / k;
		}

		return result;

	}

}
