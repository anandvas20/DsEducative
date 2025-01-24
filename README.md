import java.util.List;

public class ProductOfferingCharacteristicValue {

    private String id;
    private List<Field> field;
    private String lastModifiedTimestamp;
    private String baseType;
    private String type;

    // Getters and Setters
    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public List<Field> getField() {
        return field;
    }

    public void setField(List<Field> field) {
        this.field = field;
    }

    public String getLastModifiedTimestamp() {
        return lastModifiedTimestamp;
    }

    public void setLastModifiedTimestamp(String lastModifiedTimestamp) {
        this.lastModifiedTimestamp = lastModifiedTimestamp;
    }

    public String getBaseType() {
        return baseType;
    }

    public void setBaseType(String baseType) {
        this.baseType = baseType;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    // Nested classes
    public static class Field {
        private String name;
        private List<Entry> entry;

        // Getters and Setters
        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public List<Entry> getEntry() {
            return entry;
        }

        public void setEntry(List<Entry> entry) {
            this.entry = entry;
        }
    }

    public static class Entry {
        private Parameter parameter;

        // Getters and Setters
        public Parameter getParameter() {
            return parameter;
        }

        public void setParameter(Parameter parameter) {
            this.parameter = parameter;
        }
    }

    public static class Parameter {
        private String key;
        private String valueType;
        private List<Value> value;

        // Getters and Setters
        public String getKey() {
            return key;
        }

        public void setKey(String key) {
            this.key = key;
        }

        public String getValueType() {
            return valueType;
        }

        public void setValueType(String valueType) {
            this.valueType = valueType;
        }

        public List<Value> getValue() {
            return value;
        }

        public void setValue(List<Value> value) {
            this.value = value;
        }
    }

    public static class Value {
        private String id;
        private List<Field> field;

        // Getters and Setters
        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public List<Field> getField() {
            return field;
        }

        public void setField(List<Field> field) {
            this.field = field;
        }
    }
}