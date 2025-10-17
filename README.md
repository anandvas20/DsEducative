import java.sql.*;
import java.security.MessageDigest;
import java.util.*;

public class OracleSchemaCompare {

    private static final String DB1_URL = "jdbc:oracle:thin:@//db1-host:1521/ORCL1";
    private static final String DB2_URL = "jdbc:oracle:thin:@//db2-host:1521/ORCL2";
    private static final String DB1_USER = "A";
    private static final String DB1_PASS = "passwordA";
    private static final String DB2_USER = "B";
    private static final String DB2_PASS = "passwordB";

    public static void main(String[] args) throws Exception {
        try (
            Connection conn1 = DriverManager.getConnection(DB1_URL, DB1_USER, DB1_PASS);
            Connection conn2 = DriverManager.getConnection(DB2_URL, DB2_USER, DB2_PASS)
        ) {
            System.out.println("✅ Connected to both databases.");

            compareSchemas(conn1, conn2, DB1_USER, DB2_USER);
            compareData(conn1, conn2, DB1_USER, DB2_USER);
        }
    }

    private static void compareSchemas(Connection conn1, Connection conn2, String schema1, String schema2) throws SQLException {
        DatabaseMetaData meta1 = conn1.getMetaData();
        DatabaseMetaData meta2 = conn2.getMetaData();

        Set<String> tables1 = getTables(meta1, schema1);
        Set<String> tables2 = getTables(meta2, schema2);

        Set<String> missingInDb2 = new HashSet<>(tables1);
        missingInDb2.removeAll(tables2);

        Set<String> missingInDb1 = new HashSet<>(tables2);
        missingInDb1.removeAll(tables1);

        System.out.println("\n🧩 Schema Comparison:");
        if (missingInDb2.isEmpty() && missingInDb1.isEmpty()) {
            System.out.println("✅ Both have same tables.");
        } else {
            if (!missingInDb2.isEmpty())
                System.out.println("⚠️ Tables missing in DB2: " + missingInDb2);
            if (!missingInDb1.isEmpty())
                System.out.println("⚠️ Tables missing in DB1: " + missingInDb1);
        }

        // Compare columns for common tables
        for (String table : tables1) {
            if (tables2.contains(table)) {
                compareColumns(meta1, meta2, schema1, schema2, table);
            }
        }
    }

    private static Set<String> getTables(DatabaseMetaData meta, String schema) throws SQLException {
        Set<String> tables = new HashSet<>();
        try (ResultSet rs = meta.getTables(null, schema.toUpperCase(), "%", new String[]{"TABLE"})) {
            while (rs.next()) {
                tables.add(rs.getString("TABLE_NAME"));
            }
        }
        return tables;
    }

    private static void compareColumns(DatabaseMetaData meta1, DatabaseMetaData meta2, String schema1, String schema2, String table) throws SQLException {
        Set<String> cols1 = getColumns(meta1, schema1, table);
        Set<String> cols2 = getColumns(meta2, schema2, table);

        Set<String> missingInDb2 = new HashSet<>(cols1);
        missingInDb2.removeAll(cols2);

        Set<String> missingInDb1 = new HashSet<>(cols2);
        missingInDb1.removeAll(cols1);

        if (!missingInDb1.isEmpty() || !missingInDb2.isEmpty()) {
            System.out.println("⚠️ Column mismatch in table: " + table);
            if (!missingInDb2.isEmpty()) System.out.println("   → Missing in DB2: " + missingInDb2);
            if (!missingInDb1.isEmpty()) System.out.println("   → Missing in DB1: " + missingInDb1);
        }
    }

    private static Set<String> getColumns(DatabaseMetaData meta, String schema, String table) throws SQLException {
        Set<String> cols = new HashSet<>();
        try (ResultSet rs = meta.getColumns(null, schema.toUpperCase(), table.toUpperCase(), "%")) {
            while (rs.next()) {
                cols.add(rs.getString("COLUMN_NAME") + ":" + rs.getString("TYPE_NAME"));
            }
        }
        return cols;
    }

    private static void compareData(Connection conn1, Connection conn2, String schema1, String schema2) throws Exception {
        System.out.println("\n📊 Data Comparison (using checksum per table):");

        List<String> tables = getCommonTables(conn1, conn2, schema1, schema2);

        for (String table : tables) {
            String hash1 = computeTableHash(conn1, schema1, table);
            String hash2 = computeTableHash(conn2, schema2, table);

            if (hash1.equals(hash2)) {
                System.out.println("✅ " + table + " → identical");
            } else {
                System.out.println("⚠️ " + table + " → data differs");
            }
        }
    }

    private static List<String> getCommonTables(Connection conn1, Connection conn2, String schema1, String schema2) throws SQLException {
        Set<String> t1 = getTables(conn1.getMetaData(), schema1);
        Set<String> t2 = getTables(conn2.getMetaData(), schema2);

        List<String> common = new ArrayList<>();
        for (String t : t1) if (t2.contains(t)) common.add(t);
        return common;
    }

    private static String computeTableHash(Connection conn, String schema, String table) throws Exception {
        String sql = String.format("SELECT * FROM %s.%s", schema, table);
        try (Statement st = conn.createStatement(); ResultSet rs = st.executeQuery(sql)) {
            ResultSetMetaData md = rs.getMetaData();
            MessageDigest md5 = MessageDigest.getInstance("MD5");

            while (rs.next()) {
                StringBuilder row = new StringBuilder();
                for (int i = 1; i <= md.getColumnCount(); i++) {
                    Object val = rs.getObject(i);
                    row.append(val == null ? "NULL" : val.toString()).append("|");
                }
                md5.update(row.toString().getBytes());
            }
            return bytesToHex(md5.digest());
        } catch (SQLException e) {
            System.out.println("⚠️ Error hashing table " + table + ": " + e.getMessage());
            return "ERROR";
        }
    }

    private static String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) sb.append(String.format("%02x", b));
        return sb.toString();
    }
}
