// DB1: Schema A
private static final String DB1_URL = "jdbc:oracle:thin:@//db1-host:1521/ORCL1";
private static final String DB1_USER = "A";
private static final String DB1_PASS = "passwordA";

// DB2: Schema B
private static final String DB2_URL = "jdbc:oracle:thin:@//db2-host:1521/ORCL2";
private static final String DB2_USER = "B";
private static final String DB2_PASS = "passwordB";

public static void main(String[] args) throws Exception {
    try (
        Connection conn1 = DriverManager.getConnection(DB1_URL, DB1_USER, DB1_PASS);
        Connection conn2 = DriverManager.getConnection(DB2_URL, DB2_USER, DB2_PASS)
    ) {
        System.out.println("✅ Connected to both Oracle databases.");

        Set<String> tablesA = getTables(conn1, DB1_USER);
        Set<String> tablesB = getTables(conn2, DB2_USER);

        Set<String> commonTables = new TreeSet<>(tablesA);
        commonTables.retainAll(tablesB);

        System.out.println("\n🔍 Comparing common tables: " + commonTables.size());

        for (String table : commonTables) {
            compareColumns(conn1, conn2, DB1_USER, DB2_USER, table);
            compareTableData(conn1, conn2, DB1_USER, DB2_USER, table);
        }
    }
}

private static Set<String> getTables(Connection conn, String schema) throws SQLException {
    Set<String> tables = new HashSet<>();
    try (ResultSet rs = conn.getMetaData().getTables(null, schema.toUpperCase(), "%", new String[]{"TABLE"})) {
        while (rs.next()) {
            tables.add(rs.getString("TABLE_NAME"));
        }
    }
    return tables;
}

private static void compareColumns(Connection conn1, Connection conn2, String schema1, String schema2, String table) throws SQLException {
    Set<String> cols1 = getColumnSignatures(conn1, schema1, table);
    Set<String> cols2 = getColumnSignatures(conn2, schema2, table);

    Set<String> diff1 = new HashSet<>(cols1);
    diff1.removeAll(cols2);

    Set<String> diff2 = new HashSet<>(cols2);
    diff2.removeAll(cols1);

    if (!diff1.isEmpty() || !diff2.isEmpty()) {
        System.out.println("\n⚠️ Schema mismatch in table: " + table);
        if (!diff1.isEmpty()) System.out.println(" → In " + schema1 + " only: " + diff1);
        if (!diff2.isEmpty()) System.out.println(" → In " + schema2 + " only: " + diff2);
    }
}

private static Set<String> getColumnSignatures(Connection conn, String schema, String table) throws SQLException {
    Set<String> cols = new HashSet<>();
    try (ResultSet rs = conn.getMetaData().getColumns(null, schema.toUpperCase(), table.toUpperCase(), "%")) {
        while (rs.next()) {
            String col = rs.getString("COLUMN_NAME");
            String type = rs.getString("TYPE_NAME");
            cols.add(col + ":" + type);
        }
    }
    return cols;
}

private static void compareTableData(Connection conn1, Connection conn2, String schema1, String schema2, String table) {
    try {
        String hash1 = computeTableHash(conn1, schema1, table);
        String hash2 = computeTableHash(conn2, schema2, table);

        if (hash1.equals("ERROR") || hash2.equals("ERROR")) {
            System.out.println("⚠️ Could not compute hash for " + table);
        } else if (!hash1.equals(hash2)) {
            System.out.println("⚠️ Data mismatch in table: " + table);
        } else {
            System.out.println("✅ Data match for table: " + table);
        }
    } catch (Exception e) {
        System.out.println("❌ Error comparing data for " + table + ": " + e.getMessage());
    }
}

private static String computeTableHash(Connection conn, String schema, String table) {
    String sql = String.format("SELECT * FROM %s.%s", schema, table);
    try (
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery(sql)
    ) {
        ResultSetMetaData meta = rs.getMetaData();
        MessageDigest md = MessageDigest.getInstance("MD5");

        while (rs.next()) {
            StringBuilder row = new StringBuilder();
            for (int i = 1; i <= meta.getColumnCount(); i++) {
                Object val = rs.getObject(i);
                row.append(val == null ? "NULL" : val.toString()).append("|");
            }
            md.update(row.toString().getBytes());
        }
        return bytesToHex(md.digest());
    } catch (Exception e) {
        return "ERROR";
    }
}

private static String bytesToHex(byte[] bytes) {
    StringBuilder sb = new StringBuilder();
    for (byte b : bytes) sb.append(String.format("%02x", b));
    return sb.toString();
}
