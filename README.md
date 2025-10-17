import java.sql.*;
import java.security.MessageDigest;
import java.util.*;

public class OracleDataCompare {

    // === Update these values ===
    private static final String DB1_URL = "jdbc:oracle:thin:@//db1-host:1521/ORCL1";
    private static final String DB2_URL = "jdbc:oracle:thin:@//db2-host:1521/ORCL2";
    private static final String DB1_USER = "A";          // Schema A
    private static final String DB1_PASS = "passwordA";
    private static final String DB2_USER = "B";          // Connect as B
    private static final String DB2_PASS = "passwordB";
    private static final String DB2_SCHEMA_TO_USE = "C"; // Use schema C’s tables on DB2

    public static void main(String[] args) {
        try (
            Connection conn1 = DriverManager.getConnection(DB1_URL, DB1_USER, DB1_PASS);
            Connection conn2 = DriverManager.getConnection(DB2_URL, DB2_USER, DB2_PASS)
        ) {
            System.out.println("✅ Connected to both databases");

            List<String> commonTables = getCommonTables(conn1, conn2, DB1_USER, DB2_SCHEMA_TO_USE);

            System.out.println("\n📋 Common Tables (" + commonTables.size() + "): " + commonTables);

            for (String table : commonTables) {
                String hash1 = computeTableHash(conn1, DB1_USER, table);
                String hash2 = computeTableHash(conn2, DB2_SCHEMA_TO_USE, table);

                if (hash1.equals(hash2)) {
                    System.out.println("✅ " + table + " → identical");
                } else {
                    System.out.println("⚠️ " + table + " → data differs");
                }
            }

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static List<String> getCommonTables(Connection conn1, Connection conn2, String schema1, String schema2) throws SQLException {
        Set<String> t1 = getTables(conn1, schema1);
        Set<String> t2 = getTablesForOtherUser(conn2, schema2); // <--- changed here

        List<String> common = new ArrayList<>();
        for (String t : t1) if (t2.contains(t)) common.add(t);
        return common;
    }

    // For the connected user’s own schema
    private static Set<String> getTables(Connection conn, String schema) throws SQLException {
        Set<String> tables = new HashSet<>();
        DatabaseMetaData meta = conn.getMetaData();
        try (ResultSet rs = meta.getTables(null, schema.toUpperCase(), "%", new String[]{"TABLE"})) {
            while (rs.next()) {
                tables.add(rs.getString("TABLE_NAME"));
            }
        }
        return tables;
    }

    // For another user/schema (e.g., C) while connected as B
    private static Set<String> getTablesForOtherUser(Connection conn, String otherSchema) throws SQLException {
        Set<String> tables = new HashSet<>();
        String sql = "SELECT table_name FROM all_tables WHERE owner = ?";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, otherSchema.toUpperCase());
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    tables.add(rs.getString("TABLE_NAME"));
                }
            }
        }
        return tables;
    }

    private static String computeTableHash(Connection conn, String schema, String table) {
        String sql = "SELECT * FROM " + schema + "." + table;
        try (Statement st = conn.createStatement(ResultSet.TYPE_FORWARD_ONLY, ResultSet.CONCUR_READ_ONLY);
             ResultSet rs = st.executeQuery(sql)) {

            ResultSetMetaData md = rs.getMetaData();
            MessageDigest md5 = MessageDigest.getInstance("MD5");

            int colCount = md.getColumnCount();

            while (rs.next()) {
                StringBuilder row = new StringBuilder();
                for (int i = 1; i <= colCount; i++) {
                    Object val = rs.getObject(i);
                    row.append(val == null ? "NULL" : val.toString()).append("|");
                }
                md5.update(row.toString().getBytes());
            }

            return bytesToHex(md5.digest());

        } catch (Exception e) {
            System.out.println("⚠️ Error hashing " + schema + "." + table + ": " + e.getMessage());
            return "ERROR";
        }
    }

    private static String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) sb.append(String.format("%02x", b));
        return sb.toString();
    }
}