    task automatic qualify_prefetch_fault;
        logic [31:0] status, partial_bytes;
        bit cancelling;
        cancelling = injected_fault != 10;
        write_reg(8'h30,256,4'hf,0,0,OKAY);
        write_reg(8'h34,0,4'hf,0,0,OKAY);
        write_reg(8'h38,1,4'hf,0,0,OKAY);
        while (!dut.ddr_mac) tick();
        if (commands != 8 || beats != 64 || dut.ddr_group != 0)
            $fatal(1,"Did not enter MAC on fresh group zero");
        if (injected_fault == 11) hold_ar = 1;
        await_transport(injected_fault != 11);
        if (!dut.ddr_mac || dut.projection_reader.next_fetch_group != 1)
            $fatal(1,"Did not exercise the outstanding next group during MAC");
        if (injected_fault == 10) begin
            inject_bad_resp = 1;
            while (!dut.ddr_fault) tick();
            if (dut.ddr_mac || dut.ddr_operand_read || dut.core.logits.result_valid)
                $fatal(1,"Prefetch fault did not stop the score lanes");
            repeat(80) tick();
            read_reg(8'h28,0,OKAY,status);
            if (!status[1] || !status[2] || status[11:8] != 5)
                $fatal(1,"Prefetch fault did not terminate the request: %h",status);
            read_reg(8'h68,0,OKAY,partial_bytes);
            if (partial_bytes>=512) $fatal(1,"Faulting overlap finished first group");
            check_read(8'h64,5);
            check_read(8'h74,1);
        end else begin
            if (injected_fault == 12) begin
                while (beats < 67) tick();
                hold_r = 1;
            end
            check_read(8'h64,3);
            write_reg(8'h64,0,4'hf,0,0,SLVERR);
        end
        write_reg(8'h1c,2,4'hf,0,0,OKAY);
        check_read(8'h60,0);
        check_read(8'h64,cancelling ? 2 : 8);
        check_read(8'h68,0);
        check_read(8'h74,0);
        if (cancelling) begin
            write_reg(8'h60,DDR_BASE,4'hf,0,0,SLVERR);
            hold_ar = 0;
            hold_r = 0;
            repeat(80) tick();
        end
        check_read(8'h64,8);
        if (commands != 9 || beats != 72)
            $fatal(1,"Prefetch recovery command / response count %d / %d",commands,beats);
        check_read(8'h6c,0);
        check_read(8'h70,0);
        word_count = 0;
        for (integer bank=0;bank<15;bank=bank+1) begin
            if (bank_length(bank)!=0) begin
                write_reg(8'h04,32'(bank),4'hf,1,0,OKAY);write_reg(8'h08,0,4'hf,2,0,OKAY);
                for (integer address=0;address<bank_length(bank);address=address+1) begin
                    write_reg(8'h0c,words[word_count],4'hf,0,0,OKAY);word_count=word_count+1;
                end
            end
        end
        @(negedge aclk);
        burst_index = 0;
        inject_bad_resp = 0;
        write_reg(8'h60,DDR_BASE,4'hf,0,0,OKAY);
        write_reg(8'h64,1,4'hf,0,0,OKAY);
        run_bos(0);
        check_read(8'h6c,320);
        check_read(8'h70,2560);
        check_read(8'h68,20480);
        if (commands != 329) $fatal(1,"Recovery did not refetch the entire score matrix");
        $display("PASS DDR prefetch fault or cancel %0d, exact freshly fetched BOS logits",injected_fault);
        $finish;
    endtask
