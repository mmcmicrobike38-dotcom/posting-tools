import { Search } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const searchSchema = z.object({
  query: z.string().max(120)
});

type SearchFormValues = z.infer<typeof searchSchema>;

type SearchBarProps = {
  placeholder?: string;
  onSearch?: (query: string) => void;
};

export function SearchBar({ placeholder = "Search", onSearch }: SearchBarProps) {
  const { register, handleSubmit } = useForm<SearchFormValues>({ defaultValues: { query: "" } });

  const submit = (values: SearchFormValues) => {
    const parsed = searchSchema.safeParse(values);
    if (parsed.success) onSearch?.(parsed.data.query);
  };

  return (
    <form className="slv3-searchbar" onSubmit={handleSubmit(submit)}>
      <Search size={16} />
      <input {...register("query")} placeholder={placeholder} />
    </form>
  );
}
