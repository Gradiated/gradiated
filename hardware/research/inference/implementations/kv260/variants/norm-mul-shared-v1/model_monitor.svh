
// Independent trace of every magnitude product and accepted normalisation result.
integer products_file, norm_outputs_file, shared_owner_file;
integer observed_norm_products[3];
integer observed_norm_outputs[3];
integer observed_grants[3];
integer cycle_count = 0;
integer grant_cycle = 0;
logic [2:0] granted_owner = 0;

initial begin
    products_file = $fopen("norm-products.txt", "w");
    norm_outputs_file = $fopen("norm-outputs.txt", "w");
    shared_owner_file = $fopen("norm-ownership.txt", "w");
    if (!products_file || !norm_outputs_file || !shared_owner_file)
        $fatal(1, "Cannot open normalization traces");
end

task automatic observe_product(input int client, input logic [63:0] a, b,
        input logic negative, input logic [127:0] value);
    observed_norm_products[client]++;
    $fwrite(products_file, "%0d %0d %016x %016x %0d %032x\n",
            seen_inputs, client, a, b, negative, value);
endtask

task automatic observe_norm_output(input int client, input logic [4:0] index,
        input logic signed [15:0] value, input logic saturated, error);
    observed_norm_outputs[client]++;
    $fwrite(norm_outputs_file, "%0d %0d %0d %0d %0d %0d\n",
            seen_inputs, client, index, value, saturated, error);
endtask

always @(posedge aclk) if (aresetn && observing) begin
    if (!$onehot0({dut.core.nf_busy,dut.core.n2_busy,dut.core.n1_busy}))
        $fatal(1, "Transformer scheduled multiple normalization instances");
    cycle_count++;
    // SCALAR_OBSERVATIONS
    // SHARED_OWNERSHIP
end

final begin
    if (granted_owner != 0)
        $fatal(1, "Normalization multiplier still owned at the end of the request");
    for (int i=0; i<3; i++)
        $fwrite(shared_owner_file, "%0d %0d %0d %0d\n",
                i, observed_norm_products[i], observed_norm_outputs[i], observed_grants[i]);
    $fclose(products_file);
    $fclose(norm_outputs_file);
    $fclose(shared_owner_file);
end
