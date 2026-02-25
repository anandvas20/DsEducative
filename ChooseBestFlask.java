import java.util.*;

/*
===========================================================
Problem: Choose the Best Flask
===========================================================

An e-commerce company receives product orders of different volumes.

There are multiple flask types. Each flask type has multiple
capacity markings.

To fulfill all orders:
- You must choose ONE flask type.
- Each order must be assigned to a marking of that flask.
- The marking capacity must be >= order volume.
- Waste for one order = (marking - order).
- Total waste = sum of waste for all orders.

If a flask cannot fulfill ALL orders, discard it.

Return the flask ID with minimum total waste.
If multiple flasks have same minimum waste, return smallest ID.
If no flask can fulfill all orders, return -1.

-----------------------------------------------------------
Constraints:
1 ≤ orders.size() ≤ 10^5
1 ≤ flaskTypesCount ≤ 10^4
1 ≤ markings.size() ≤ 10^5
0 ≤ flaskId < flaskTypesCount
1 ≤ order, marking ≤ 10^9
-----------------------------------------------------------
Time Complexity:
O(N log N + F * O * log M)

Where:
N = number of orders
F = number of flask types
M = number of markings per flask
O = number of orders

===========================================================
*/

public class ChooseBestFlask {

    public static int chooseFlask(List<Integer> orders,
                                  int flaskTypesCount,
                                  List<List<Integer>> markings) {

        // Step 1: Sort orders
        Collections.sort(orders);

        // Step 2: Build flaskId -> markings map
        Map<Integer, List<Integer>> flaskMap = new HashMap<>();

        for (List<Integer> mark : markings) {
            int flaskId = mark.get(0);
            int capacity = mark.get(1);

            flaskMap.computeIfAbsent(flaskId, k -> new ArrayList<>())
                    .add(capacity);
        }

        long minWaste = Long.MAX_VALUE;
        int bestFlaskId = -1;

        // Step 3: Evaluate each flask
        for (int flaskId : flaskMap.keySet()) {

            List<Integer> capacities = flaskMap.get(flaskId);
            Collections.sort(capacities);

            long totalWaste = 0;
            boolean possible = true;

            for (int order : orders) {

                // Binary search: first capacity >= order
                int index = Collections.binarySearch(capacities, order);

                if (index < 0) {
                    index = -(index + 1);
                }

                if (index == capacities.size()) {
                    possible = false;
                    break;
                }

                totalWaste += (capacities.get(index) - order);
            }

            if (possible) {
                if (totalWaste < minWaste ||
                   (totalWaste == minWaste && flaskId < bestFlaskId)) {

                    minWaste = totalWaste;
                    bestFlaskId = flaskId;
                }
            }
        }

        return bestFlaskId;
    }

    // ========================
    // Example Test Cases
    // ========================
    public static void main(String[] args) {

        List<Integer> orders = Arrays.asList(4, 6, 8);

        List<List<Integer>> markings = Arrays.asList(
                Arrays.asList(0, 5),
                Arrays.asList(0, 7),
                Arrays.asList(0, 10),
                Arrays.asList(1, 6),
                Arrays.asList(1, 8),
                Arrays.asList(1, 9)
        );

        int result = chooseFlask(orders, 2, markings);
        System.out.println("Best Flask ID: " + result);
        // Expected Output: 0
    }
}
